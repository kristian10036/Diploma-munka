from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.db import _write_audit_event, get_db
from app.runtime import DEVICE_BASELINE_SETTINGS
from app.schemas import DeviceBaselineDeactivateRequest, DeviceBaselineSaveRequest
from app.services.baseline import compute_baseline_comparison, deactivate_baseline, save_baseline
from app.services.persistence import ensure_location

router = APIRouter()


def _grace_seconds(protocol: str) -> float:
    return (
        DEVICE_BASELINE_SETTINGS.wifi_missing_grace_seconds
        if protocol == "wifi"
        else DEVICE_BASELINE_SETTINGS.bluetooth_missing_grace_seconds
    )


@router.post("/api/device-baseline/save")
def save_device_baseline(request: DeviceBaselineSaveRequest):
    with get_db() as conn:
        with conn.cursor() as cur:
            location_id = ensure_location(cur, request.location_name)
            result = save_baseline(
                cur,
                protocol=request.protocol,
                location_name=request.location_name,
                location_id=location_id,
                session_id=request.measurement_session_id,
                operator=(request.operator or "operator").strip()[:200],
                notes=request.notes,
            )
        conn.commit()
    _write_audit_event(
        "device_baseline.saved",
        entity_type="device_baseline",
        entity_id=None,
        actor=request.operator or "operator",
        details=result,
    )
    return result


@router.post("/api/device-baseline/deactivate")
def deactivate_device_baseline(request: DeviceBaselineDeactivateRequest):
    with get_db() as conn:
        with conn.cursor() as cur:
            result = deactivate_baseline(
                cur, protocol=request.protocol, location_name=request.location_name
            )
        conn.commit()
    _write_audit_event(
        "device_baseline.deactivated",
        entity_type="device_baseline",
        entity_id=None,
        actor="operator",
        details=result,
    )
    return result


@router.get("/api/device-baseline/compare")
def compare_device_baseline(
    protocol: str,
    location_name: str,
    measurement_session_id: uuid.UUID | None = None,
):
    with get_db() as conn:
        with conn.cursor() as cur:
            return compute_baseline_comparison(
                cur,
                protocol=protocol,
                location_name=location_name,
                session_id=measurement_session_id,
                grace_seconds=_grace_seconds(protocol),
            )
