from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from psycopg.types.json import Jsonb

from app.db import get_db, validated_optional_uuid, write_audit_event
from app.metrics import REFERENCE_IMPORTED_POINTS, REFERENCE_IMPORTS_TOTAL
from app.services.persistence import ensure_location
from app.services.references import ReferenceImportError, importer_for, peak_preserving_resample
from app.utils.uploads import REFERENCE_IMPORT_LIMIT_BYTES, read_bounded_upload

router = APIRouter(tags=["references"])
MAX_REFERENCE_BYTES = REFERENCE_IMPORT_LIMIT_BYTES
MAX_REFERENCE_POINTS = 65_536
REFERENCE_KEY_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,128}")
CREATION_SOURCES = {"live", "import", "replay", "converted"}


def _read_upload(file: UploadFile) -> tuple[str, bytes]:
    filename = Path(file.filename or "reference").name
    payload = read_bounded_upload(
        file,
        max_bytes=MAX_REFERENCE_BYTES,
        empty_detail={
            "code": "empty_reference_file",
            "message": "Üres referencia nem importálható.",
        },
        too_large_detail={
            "code": "reference_too_large",
            "message": "A referencia legfeljebb 64 MiB lehet.",
        },
    )
    return filename, payload


def _parse_datetime(value: str | None, field: str) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": f"invalid_{field}", "message": f"A {field} ISO-8601 dátum legyen."},
        ) from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _import_error(exc: ReferenceImportError) -> HTTPException:
    status = 415 if exc.code.startswith("unsupported") else 422
    return HTTPException(status_code=status, detail={"code": exc.code, "message": str(exc)})


@router.post("/api/references/inspect")
def inspect_reference(file: UploadFile = File(...)) -> dict[str, Any]:
    filename, payload = _read_upload(file)
    try:
        importer = importer_for(filename, file.content_type or "", payload[:512])
        result = importer.inspect(payload)
        if result.get("supported") is False:
            raise ReferenceImportError(
                "unsupported_peak_format",
                "A .peak fájl közvetlenül nem importálható. "
                "Exportálj CSV-t az OSCOR Data Viewerből.",
            )
        return {"filename": filename, **result}
    except ReferenceImportError as exc:
        raise _import_error(exc) from exc


@router.post("/api/references/import", status_code=201)
def import_versioned_reference(
    file: UploadFile = File(...),
    reference_key: str | None = Form(None),
    location_name: str | None = Form(None),
    device_name: str | None = Form(None),
    source_type: str | None = Form(None),
    antenna: str | None = Form(None),
    downconverter_profile: str | None = Form(None),
    rbw_hz: float | None = Form(None),
    vbw_hz: float | None = Form(None),
    measured_at: str | None = Form(None),
    operator_name: str | None = Form(None),
    notes: str | None = Form(None),
    valid_from: str | None = Form(None),
    valid_until: str | None = Form(None),
    creation_source: str = Form("import"),
    activate: bool = Form(False),
):
    filename, payload = _read_upload(file)
    creation_source = creation_source.strip().casefold()
    if creation_source not in CREATION_SOURCES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_creation_source",
                "message": "Érvénytelen létrehozási forrás.",
            },
        )
    measured = _parse_datetime(measured_at, "measured_at")
    starts = _parse_datetime(valid_from, "valid_from")
    ends = _parse_datetime(valid_until, "valid_until")
    if starts and ends and starts >= ends:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_validity_window",
                "message": "A valid_until legyen későbbi a valid_from értéknél.",
            },
        )
    try:
        importer = importer_for(filename, file.content_type or "", payload[:512])
        imported = importer.import_points(payload)
        points = peak_preserving_resample(imported.points, MAX_REFERENCE_POINTS)
    except ReferenceImportError as exc:
        REFERENCE_IMPORTS_TOTAL.labels(
            format=Path(filename).suffix.casefold().lstrip(".") or "unknown", result="rejected"
        ).inc()
        raise _import_error(exc) from exc

    key = (reference_key or Path(filename).stem).strip()
    if not REFERENCE_KEY_PATTERN.fullmatch(key):
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_reference_key", "message": "Érvénytelen referenciaazonosító."},
        )
    frequencies = [point[0] for point in points]
    differences = {
        frequencies[index] - frequencies[index - 1] for index in range(1, len(frequencies))
    }
    step = next(iter(differences)) if len(differences) == 1 else None
    checksum = hashlib.sha256(payload).hexdigest()
    metadata = dict(imported.metadata)
    metadata.update(
        {
            "original_point_count": len(imported.points),
            "resampled": len(points) != len(imported.points),
        }
    )

    with get_db() as conn:
        with conn.cursor() as cur:
            location_id = (
                ensure_location(cur, location_name.strip())
                if location_name and location_name.strip()
                else None
            )
            # Prevent two concurrent imports from selecting the same next version.
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (key,))
            cur.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS version FROM spectrum_references "
                "WHERE reference_key=%s",
                (key,),
            )
            version = cur.fetchone()["version"]
            if activate:
                cur.execute(
                    "UPDATE spectrum_references SET is_active=false, updated_at=now() "
                    "WHERE reference_key=%s AND archived_at IS NULL",
                    (key,),
                )
            cur.execute(
                """
                INSERT INTO spectrum_references
                  (reference_key, version, location_id, location_name, device_name, source_type,
                   antenna, downconverter_profile, start_frequency_hz, stop_frequency_hz,
                   step_frequency_hz, rbw_hz, vbw_hz, measured_at, operator_name, notes,
                   checksum_sha256, is_active, valid_from, valid_until, creation_source,
                   original_filename, import_format, point_count, metadata)
                VALUES
                  (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    key,
                    version,
                    location_id,
                    location_name,
                    device_name,
                    source_type,
                    antenna,
                    downconverter_profile,
                    frequencies[0],
                    frequencies[-1],
                    step,
                    rbw_hz,
                    vbw_hz,
                    measured,
                    operator_name,
                    notes,
                    checksum,
                    activate,
                    starts,
                    ends,
                    creation_source,
                    filename,
                    imported.import_format,
                    len(points),
                    Jsonb(metadata),
                ),
            )
            reference = cur.fetchone()
            point_time = measured or datetime.now(timezone.utc)
            cur.executemany(
                """
                INSERT INTO reference_spectrum_points
                  (time, reference_id, location_id, location_name, device_name, source_file,
                   measured_frequency_hz, actual_rf_frequency_hz, power_dbm, rbw_hz, vbw_hz,
                   antenna, downconverter_profile, raw_row)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                [
                    (
                        point_time,
                        str(reference["id"]),
                        location_id,
                        location_name or "unspecified",
                        device_name,
                        filename,
                        frequency,
                        frequency,
                        power,
                        round(rbw_hz) if rbw_hz else None,
                        round(vbw_hz) if vbw_hz else None,
                        antenna,
                        downconverter_profile,
                        Jsonb({"import_format": imported.import_format}),
                    )
                    for frequency, power in points
                ],
            )
        conn.commit()

    REFERENCE_IMPORTS_TOTAL.labels(format=imported.import_format, result="accepted").inc()
    REFERENCE_IMPORTED_POINTS.observe(len(points))
    write_audit_event(
        "spectrum.reference.imported",
        entity_type="spectrum_reference",
        entity_id=str(reference["id"]),
        details={
            "reference_key": key,
            "version": version,
            "format": imported.import_format,
            "checksum_sha256": checksum,
        },
    )
    return reference


@router.get("/api/references")
def list_versioned_references(
    limit: int = 100,
    include_archived: bool = False,
    reference_key: str | None = None,
    location_name: str | None = None,
    active_only: bool = False,
):
    safe = min(max(limit, 1), 500)
    conditions: list[str] = []
    parameters: list[Any] = []
    if not include_archived:
        conditions.append("archived_at IS NULL")
    if reference_key:
        conditions.append("reference_key=%s")
        parameters.append(reference_key)
    if location_name and location_name.strip():
        conditions.append("lower(location_name) = lower(%s)")
        parameters.append(location_name.strip())
    if active_only:
        conditions.append("is_active=true")
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    parameters.append(safe)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM spectrum_references{where} "
                "ORDER BY reference_key, version DESC LIMIT %s",
                parameters,
            )
            rows = cur.fetchall()
    return {"items": rows, "count": len(rows)}


@router.get("/api/references/{reference_uuid}")
def get_versioned_reference(reference_uuid: str, include_points: bool = False):
    identifier = validated_optional_uuid(reference_uuid, "reference_id")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM spectrum_references WHERE id=%s", (identifier,))
            reference = cur.fetchone()
            if reference and include_points:
                cur.execute(
                    "SELECT COALESCE(actual_rf_frequency_hz, measured_frequency_hz) "
                    "AS frequency_hz, power_dbm "
                    "FROM reference_spectrum_points WHERE reference_id=%s "
                    "ORDER BY COALESCE(actual_rf_frequency_hz, measured_frequency_hz)",
                    (identifier,),
                )
                reference["points"] = cur.fetchall()
    if not reference:
        raise HTTPException(status_code=404, detail="reference_not_found")
    return reference


@router.post("/api/references/{reference_uuid}/activate")
def activate_versioned_reference(reference_uuid: str):
    identifier = validated_optional_uuid(reference_uuid, "reference_id")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT reference_key FROM spectrum_references WHERE id=%s AND archived_at IS NULL",
                (identifier,),
            )
            found = cur.fetchone()
            if not found:
                raise HTTPException(status_code=404, detail="reference_not_found")
            cur.execute(
                "UPDATE spectrum_references SET is_active=(id=%s), updated_at=now() "
                "WHERE reference_key=%s AND archived_at IS NULL",
                (identifier, found["reference_key"]),
            )
            cur.execute("SELECT * FROM spectrum_references WHERE id=%s", (identifier,))
            row = cur.fetchone()
        conn.commit()
    write_audit_event(
        "spectrum.reference.activated", entity_type="spectrum_reference", entity_id=identifier
    )
    return row


@router.post("/api/references/{reference_uuid}/deactivate")
def deactivate_versioned_reference(reference_uuid: str):
    identifier = validated_optional_uuid(reference_uuid, "reference_id")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE spectrum_references SET is_active=false, updated_at=now() "
                "WHERE id=%s RETURNING *",
                (identifier,),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail="reference_not_found")
    write_audit_event(
        "spectrum.reference.deactivated", entity_type="spectrum_reference", entity_id=identifier
    )
    return row


@router.get("/api/references/{reference_uuid}/export")
def export_versioned_reference(reference_uuid: str, format: str = "json"):
    reference = get_versioned_reference(reference_uuid, include_points=True)
    points = reference.pop("points")
    filename = f"{reference['reference_key']}_v{reference['version']}"
    normalized_format = format.casefold()
    if normalized_format == "json":
        body = json.dumps(
            {"metadata": reference, "points": points}, default=str, ensure_ascii=False, indent=2
        )
        return Response(
            body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}.json"'},
        )
    if normalized_format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "reference_id",
                "reference_key",
                "version",
                "layer_type",
                "display_color",
                "location_name",
                "device_name",
                "measured_at",
                "frequency_hz",
                "power_dbm",
            ],
        )
        writer.writeheader()
        for point in points:
            writer.writerow(
                {
                    "reference_id": reference["id"],
                    "reference_key": reference["reference_key"],
                    "version": reference["version"],
                    "layer_type": "reference",
                    "display_color": reference.get("metadata", {}).get("display_color", "#ff5252"),
                    "location_name": reference.get("location_name"),
                    "device_name": reference.get("device_name"),
                    "measured_at": reference.get("measured_at"),
                    "frequency_hz": point["frequency_hz"],
                    "power_dbm": point["power_dbm"],
                }
            )
        return Response(
            output.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
        )
    raise HTTPException(
        status_code=422,
        detail={
            "code": "unsupported_export_format",
            "message": "Csak json vagy csv export támogatott.",
        },
    )
