from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from psycopg import sql
from pydantic import BaseModel

from app.db import _write_audit_event, get_db

router = APIRouter()

# Csak ezek a (folyamatosan növő) hypertable-ök tisztíthatók ezzel az eszközzel.
# A tábla- és időoszlop-nevek fixek, sosem érkeznek kérésből SQL-be interpolálva.
_RETENTION_DATASETS: dict[str, dict[str, str]] = {
    "spectrum_peaks": {"time_column": "time", "label": "Mentett spektrum csúcsok"},
    "wifi_observations": {"time_column": "time", "label": "Wi-Fi megfigyelések"},
    "bluetooth_observations": {"time_column": "time", "label": "Bluetooth megfigyelések"},
    "anomalies": {"time_column": "time", "label": "Anomáliák"},
}


def _dataset_config(dataset: str) -> dict[str, str]:
    config = _RETENTION_DATASETS.get(dataset)
    if not config:
        raise HTTPException(status_code=422, detail="unsupported_dataset")
    return config


def _parse_older_than(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid_older_than") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@router.get("/api/admin/retention/datasets")
def list_retention_datasets():
    return {"items": [{"dataset": key, **value} for key, value in _RETENTION_DATASETS.items()]}


@router.get("/api/admin/retention/preview")
def preview_retention(dataset: str, older_than: str):
    config = _dataset_config(dataset)
    cutoff = _parse_older_than(older_than)
    time_column = sql.Identifier(config["time_column"])
    table = sql.Identifier(dataset)
    query = sql.SQL(
        "SELECT count(*) AS row_count, min({col}) AS oldest, max({col}) AS newest FROM {table} WHERE {col} < %s"
    ).format(col=time_column, table=table)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (cutoff,))
            row = cur.fetchone()
    return {
        "dataset": dataset,
        "cutoff": cutoff,
        "row_count": row["row_count"],
        "oldest": row["oldest"],
        "newest": row["newest"],
    }


class RetentionPurgeRequest(BaseModel):
    dataset: str
    older_than: str
    confirm: bool = False


@router.post("/api/admin/retention/purge")
def purge_retention(request: RetentionPurgeRequest):
    if not request.confirm:
        raise HTTPException(status_code=422, detail="confirmation_required")
    _dataset_config(request.dataset)
    cutoff = _parse_older_than(request.older_than)
    # drop_chunks fizikailag eldobja az érintett TimescaleDB chunk-fájlokat, ezért
    # ez ténylegesen felszabadítja a lemezterületet (egy sima DELETE csak holt
    # sorokat hagyna a fájlban, amíg az autovacuum/VACUUM FULL nem futna le).
    # A regclass argumentum csak string literálként + ::regclass cast-tal helyes,
    # sql.Identifier-ként a parser oszlophivatkozásnak nézné a táblanevet.
    query = sql.SQL("SELECT drop_chunks({table}::regclass, older_than => %s) AS dropped_chunk").format(
        table=sql.Literal(request.dataset)
    )
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (cutoff,))
            dropped_chunks = [row["dropped_chunk"] for row in cur.fetchall()]
        conn.commit()
    _write_audit_event(
        "data_retention.purged",
        entity_type=request.dataset,
        details={"older_than": request.older_than, "dropped_chunks": len(dropped_chunks)},
    )
    return {"dataset": request.dataset, "cutoff": cutoff, "dropped_chunks": len(dropped_chunks)}
