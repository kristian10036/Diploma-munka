from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.metrics import RECORDING_DISK_FREE_BYTES, RECORDING_LOW_DISK
from app.db import get_db
from app.runtime import RECORDING_CATALOG, RECORDING_SETTINGS, RECORDING_STORAGE

router = APIRouter(prefix="/api/recordings", tags=["recordings"])


@router.get("/capabilities")
def get_recording_capabilities():
    return {
        "implemented": True,
        "types": {
            "spectrum": {
                "status": "ready_when_rf_agent_available",
                "format": "SpectrumFrame NDJSON with optional zstd",
                "post_demodulation_capable": False,
                "note": "A power-spectrum recording does not contain complex IQ samples.",
            },
            "iq": {
                "status": "mock_tested_hardware_not_tested",
                "format": "SigMF .sigmf-meta + .sigmf-data",
                "datatypes": ["cf32_le", "ci16_le"],
                "post_demodulation_capable": True,
            },
            "audio": {
                "status": "mock_tested_sdrangel_not_tested",
                "format": "WAV PCM signed 16-bit little-endian",
                "source": "future SDRangel or verified demodulator output",
            },
        },
        "limits": {
            "max_recording_bytes": RECORDING_SETTINGS.max_recording_bytes,
            "max_duration_seconds": RECORDING_SETTINGS.max_duration_seconds,
            "min_free_bytes": RECORDING_SETTINGS.min_free_bytes,
            "retention_days": RECORDING_SETTINGS.retention_days,
        },
    }


@router.get("/storage/status")
def get_recording_storage_status():
    status = RECORDING_STORAGE.status()
    RECORDING_DISK_FREE_BYTES.set(status.free_bytes)
    RECORDING_LOW_DISK.set(1 if status.low_disk else 0)
    return status.as_dict()


@router.get("/catalog")
def get_recording_catalog(
    verify_checksums: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
):
    try:
        items = RECORDING_CATALOG.list(verify_checksums=verify_checksums, limit=limit)
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"recording_storage_unavailable:{type(exc).__name__}") from exc
    counts: dict[str, int] = {}
    for item in items:
        key = str(item.get("recording_type") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return {"items": items, "count": len(items), "counts_by_type": counts}


@router.get("/retention/plan")
def get_recording_retention_plan():
    return RECORDING_STORAGE.retention_plan()


@router.get("/orphan-audit")
def get_recording_orphan_audit():
    """Compare filesystem spectrum recordings with DB metadata without deleting anything."""
    filesystem = RECORDING_CATALOG.list(verify_checksums=False, limit=1000)
    filesystem_ids = {str(item.get("recording_id")) for item in filesystem if item.get("recording_id")}
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT recording_id FROM spectrum_recordings ORDER BY recording_id")
                database_ids = {str(row["recording_id"]) for row in cur.fetchall()}
    except HTTPException as exc:
        return {
            "status": "database_unavailable",
            "destructive_action": False,
            "filesystem_count": len(filesystem_ids),
            "database_count": None,
            "filesystem_only": sorted(filesystem_ids),
            "database_only": [],
            "detail": exc.detail,
        }
    return {
        "status": "ok",
        "destructive_action": False,
        "filesystem_count": len(filesystem_ids),
        "database_count": len(database_ids),
        "filesystem_only": sorted(filesystem_ids - database_ids),
        "database_only": sorted(database_ids - filesystem_ids),
    }
