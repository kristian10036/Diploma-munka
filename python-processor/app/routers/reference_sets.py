from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from psycopg.types.json import Jsonb

from app.db import get_db, validated_optional_uuid, write_audit_event
from app.runtime import DEVICE_BASELINE_SETTINGS
from app.schemas import ReferenceSetCaptureRequest
from app.services.baseline import compute_baseline_comparison, save_baseline
from app.services.persistence import ensure_location
from app.utils.uploads import REFERENCE_IMPORT_LIMIT_BYTES, read_bounded_upload

router = APIRouter(tags=["reference-sets"])

REFERENCE_KEY_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,128}")
SPECTRUM_KINDS = {"snapshot", "max_hold"}
MAX_REFERENCE_POINTS = 65_536


def _clean_key(value: str) -> str:
    key = value.strip()
    if not REFERENCE_KEY_PATTERN.fullmatch(key):
        raise HTTPException(status_code=422, detail={"code": "invalid_reference_key", "message": "Érvénytelen referenciaazonosító."})
    return key


def _normalize_points(points: list[Any]) -> list[tuple[int, float]]:
    if not points or len(points) > MAX_REFERENCE_POINTS:
        raise HTTPException(status_code=422, detail={"code": "invalid_spectrum_points", "message": "1 és 65536 közötti spektrumpont szükséges."})
    normalized: list[tuple[int, float]] = []
    previous = 0
    for point in points:
        frequency = int(point.frequency_hz if hasattr(point, "frequency_hz") else point["frequency_hz"])
        power = float(point.power_dbm if hasattr(point, "power_dbm") else point["power_dbm"])
        if frequency <= 0 or frequency <= previous or not math.isfinite(power):
            raise HTTPException(status_code=422, detail={"code": "invalid_spectrum_points", "message": "A frekvenciák pozitívak és szigorúan növekvők legyenek; a dBm érték legyen véges."})
        normalized.append((frequency, power))
        previous = frequency
    return normalized


def _checksum(points: list[tuple[int, float]]) -> str:
    payload = json.dumps(points, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _step_frequency(points: list[tuple[int, float]]) -> int | None:
    frequencies = [point[0] for point in points]
    differences = {frequencies[index] - frequencies[index - 1] for index in range(1, len(frequencies))}
    return next(iter(differences)) if len(differences) == 1 else None


def _baseline_grace(protocol: str) -> float:
    return (
        DEVICE_BASELINE_SETTINGS.wifi_missing_grace_seconds
        if protocol == "wifi"
        else DEVICE_BASELINE_SETTINGS.bluetooth_missing_grace_seconds
    )


def _reference_set_components(cur, reference_set_id: str) -> dict[str, Any]:
    cur.execute(
        "SELECT id, reference_kind, point_count, is_active FROM spectrum_references WHERE reference_set_id=%s ORDER BY version DESC",
        (reference_set_id,),
    )
    spectrum = list(cur.fetchall())
    cur.execute(
        "SELECT protocol, count(*) AS count FROM device_baselines WHERE reference_set_id=%s GROUP BY protocol",
        (reference_set_id,),
    )
    baselines = {row["protocol"]: row["count"] for row in cur.fetchall()}
    return {
        "spectrum": spectrum,
        "wifi_baseline_count": int(baselines.get("wifi", 0) or 0),
        "bluetooth_baseline_count": int(baselines.get("bluetooth", 0) or 0),
    }


@router.get("/api/reference-sets")
def list_reference_sets(
    location_name: str | None = None,
    active_only: bool = False,
    include_archived: bool = False,
    limit: int = 100,
):
    safe_limit = max(1, min(limit, 500))
    conditions: list[str] = []
    parameters: list[Any] = []
    if location_name and location_name.strip():
        conditions.append("lower(location_name) = lower(%s)")
        parameters.append(location_name.strip())
    if active_only:
        conditions.append("is_active = true")
    if not include_archived:
        conditions.append("archived_at IS NULL")
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    parameters.append(safe_limit)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM reference_sets{where} ORDER BY updated_at DESC LIMIT %s", parameters)
            items = list(cur.fetchall())
    return {"items": items, "count": len(items)}


@router.get("/api/reference-sets/{reference_set_id}")
def get_reference_set(reference_set_id: str):
    identifier = validated_optional_uuid(reference_set_id, "reference_set_id")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM reference_sets WHERE id=%s", (identifier,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="reference_set_not_found")
            result = dict(row)
            result["components"] = _reference_set_components(cur, identifier)
    return result


@router.get("/api/reference-sets/{reference_set_id}/spectrum")
def get_reference_set_spectrum(reference_set_id: str):
    identifier = validated_optional_uuid(reference_set_id, "reference_set_id")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM spectrum_references WHERE reference_set_id=%s ORDER BY is_active DESC, version DESC LIMIT 1",
                (identifier,),
            )
            reference = cur.fetchone()
            if not reference:
                raise HTTPException(status_code=404, detail="spectrum_reference_not_found")
            cur.execute(
                "SELECT COALESCE(actual_rf_frequency_hz, measured_frequency_hz) AS frequency_hz, power_dbm "
                "FROM reference_spectrum_points WHERE reference_id=%s ORDER BY COALESCE(actual_rf_frequency_hz, measured_frequency_hz)",
                (str(reference["id"]),),
            )
            points = list(cur.fetchall())
    return {"items": points, "count": len(points)}


@router.post("/api/reference-sets/capture", status_code=201)
def capture_reference_set(request: ReferenceSetCaptureRequest):
    key = _clean_key(request.reference_key)
    kind = request.spectrum_reference_kind.strip().casefold()
    if kind not in SPECTRUM_KINDS:
        raise HTTPException(status_code=422, detail={"code": "invalid_spectrum_reference_kind", "message": "snapshot vagy max_hold támogatott."})
    location_name = request.location_name.strip()
    points = _normalize_points(request.spectrum_points)
    now = datetime.now(timezone.utc)
    checksum = _checksum(points)
    step = _step_frequency(points)
    session_id = validated_optional_uuid(request.measurement_session_id, "measurement_session_id") if request.measurement_session_id else None
    metadata = dict(request.spectrum_metadata or {})
    metadata.update({"layer_type": "reference", "reference_kind": kind})

    with get_db() as conn:
        with conn.cursor() as cur:
            location_id = ensure_location(cur, location_name)
            if session_id:
                cur.execute("SELECT id FROM measurement_sessions WHERE id=%s", (session_id,))
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="measurement_session_not_found")
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (key,))
            cur.execute("SELECT COALESCE(MAX(version), 0) + 1 AS version FROM reference_sets WHERE reference_key=%s", (key,))
            version = cur.fetchone()["version"]
            if request.activate:
                cur.execute(
                    "UPDATE reference_sets SET is_active=false, updated_at=now() "
                    "WHERE lower(location_name)=lower(%s) AND archived_at IS NULL",
                    (location_name,),
                )
            cur.execute(
                """
                INSERT INTO reference_sets
                  (reference_key, version, name, location_id, location_name,
                   source_measurement_session_id, capture_started_at, capture_ended_at,
                   status, is_active, created_by, notes, metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'ready',%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    key, version, request.name.strip(), location_id, location_name,
                    session_id, now, now, request.activate, request.operator_name,
                    request.notes, Jsonb({"spectrum_reference_kind": kind}),
                ),
            )
            reference_set = cur.fetchone()
            cur.execute(
                """
                INSERT INTO spectrum_references
                  (reference_key, version, location_id, location_name, device_name, source_type,
                   start_frequency_hz, stop_frequency_hz, step_frequency_hz, measured_at,
                   operator_name, notes, checksum_sha256, is_active, creation_source,
                   original_filename, import_format, point_count, metadata,
                   reference_set_id, measurement_session_id, reference_kind, window_start,
                   window_end, frame_count)
                VALUES (%s,%s,%s,%s,%s,'spectrum_monitor',%s,%s,%s,%s,%s,%s,%s,%s,'live',
                        'reference_set_capture','live_spectrum_capture',%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    key, version, location_id, location_name, metadata.get("device_name"),
                    points[0][0], points[-1][0], step, now, request.operator_name,
                    request.notes, checksum, request.activate, len(points), Jsonb(metadata),
                    reference_set["id"], session_id, kind, metadata.get("window_start"),
                    metadata.get("window_end"), metadata.get("frame_count"),
                ),
            )
            spectrum_reference = cur.fetchone()
            cur.executemany(
                """
                INSERT INTO reference_spectrum_points
                  (time, reference_id, location_id, location_name, device_name, source_file,
                   measured_frequency_hz, actual_rf_frequency_hz, power_dbm, raw_row)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                [
                    (
                        now, str(spectrum_reference["id"]), location_id, location_name,
                        metadata.get("device_name"), "reference_set_capture", frequency, frequency,
                        power, Jsonb({"reference_set_id": str(reference_set["id"]), "reference_kind": kind}),
                    )
                    for frequency, power in points
                ],
            )
            baseline_results: dict[str, Any] = {}
            for protocol, include in (("wifi", request.include_wifi), ("bluetooth", request.include_bluetooth)):
                if not include:
                    continue
                try:
                    baseline_results[protocol] = save_baseline(
                        cur,
                        protocol=protocol,
                        location_name=location_name,
                        location_id=location_id,
                        session_id=session_id,
                        operator=request.operator_name,
                        notes=request.notes,
                        reference_set_id=str(reference_set["id"]),
                    )
                except HTTPException as exc:
                    if exc.status_code == 409:
                        baseline_results[protocol] = {"protocol": protocol, "saved_entries": 0, "warning": "no_session_observations"}
                    else:
                        raise
        conn.commit()
    write_audit_event("reference_set.captured", entity_type="reference_set", entity_id=str(reference_set["id"]))
    return {"reference_set": reference_set, "spectrum_reference": spectrum_reference, "baselines": baseline_results}


@router.post("/api/reference-sets/{reference_set_id}/activate")
def activate_reference_set(reference_set_id: str):
    identifier = validated_optional_uuid(reference_set_id, "reference_set_id")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT location_name FROM reference_sets WHERE id=%s AND archived_at IS NULL", (identifier,))
            found = cur.fetchone()
            if not found:
                raise HTTPException(status_code=404, detail="reference_set_not_found")
            cur.execute(
                "UPDATE reference_sets SET is_active=(id=%s), updated_at=now() "
                "WHERE lower(location_name)=lower(%s) AND archived_at IS NULL",
                (identifier, found["location_name"]),
            )
            cur.execute("UPDATE spectrum_references SET is_active=(reference_set_id=%s), updated_at=now() WHERE reference_set_id IN (SELECT id FROM reference_sets WHERE lower(location_name)=lower(%s))", (identifier, found["location_name"]))
            cur.execute("SELECT * FROM reference_sets WHERE id=%s", (identifier,))
            row = cur.fetchone()
        conn.commit()
    return row


@router.post("/api/reference-sets/{reference_set_id}/deactivate")
def deactivate_reference_set(reference_set_id: str):
    identifier = validated_optional_uuid(reference_set_id, "reference_set_id")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE reference_sets SET is_active=false, updated_at=now() WHERE id=%s RETURNING *", (identifier,))
            row = cur.fetchone()
            if row:
                cur.execute("UPDATE spectrum_references SET is_active=false, updated_at=now() WHERE reference_set_id=%s", (identifier,))
        conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail="reference_set_not_found")
    return row


def _export_payload(cur, reference_set_id: str) -> dict[str, Any]:
    cur.execute("SELECT * FROM reference_sets WHERE id=%s", (reference_set_id,))
    reference_set = cur.fetchone()
    if not reference_set:
        raise HTTPException(status_code=404, detail="reference_set_not_found")
    cur.execute("SELECT * FROM spectrum_references WHERE reference_set_id=%s ORDER BY version DESC LIMIT 1", (reference_set_id,))
    spectrum_reference = cur.fetchone()
    spectrum_points: list[Any] = []
    if spectrum_reference:
        cur.execute(
            "SELECT COALESCE(actual_rf_frequency_hz, measured_frequency_hz) AS frequency_hz, power_dbm "
            "FROM reference_spectrum_points WHERE reference_id=%s ORDER BY COALESCE(actual_rf_frequency_hz, measured_frequency_hz)",
            (str(spectrum_reference["id"]),),
        )
        spectrum_points = list(cur.fetchall())
    cur.execute("SELECT * FROM device_baselines WHERE reference_set_id=%s ORDER BY protocol, stable_identity", (reference_set_id,))
    baselines = list(cur.fetchall())
    return {
        "manifest": {"schema": "reference_set_export", "version": 1, "exported_at": datetime.now(timezone.utc).isoformat()},
        "reference_set": reference_set,
        "spectrum_reference": spectrum_reference,
        "spectrum_points": spectrum_points,
        "device_baselines": baselines,
    }


@router.get("/api/reference-sets/{reference_set_id}/export")
def export_reference_set(reference_set_id: str, format: str = "json"):
    identifier = validated_optional_uuid(reference_set_id, "reference_set_id")
    if format.casefold() != "json":
        raise HTTPException(status_code=422, detail={"code": "unsupported_export_format", "message": "Egyelőre JSON reference_set export támogatott."})
    with get_db() as conn:
        with conn.cursor() as cur:
            payload = _export_payload(cur, identifier)
    filename = f"{payload['reference_set']['reference_key']}_reference_set_v{payload['reference_set']['version']}.json"
    body = json.dumps(payload, default=str, ensure_ascii=False, indent=2)
    return Response(body, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/api/reference-sets/import", status_code=201)
def import_reference_set(file: UploadFile = File(...), activate: bool = True):
    filename = Path(file.filename or "reference_set.json").name
    payload = read_bounded_upload(
        file,
        max_bytes=REFERENCE_IMPORT_LIMIT_BYTES,
        empty_detail={"code": "empty_reference_set", "message": "Üres reference_set nem importálható."},
        too_large_detail={"code": "reference_set_too_large", "message": "A referencia csomag legfeljebb 64 MiB lehet."},
    )
    try:
        data = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_reference_set_json", "message": "Érvénytelen JSON referencia csomag."}) from exc
    reference_set = data.get("reference_set") if isinstance(data, dict) else None
    spectrum_points = data.get("spectrum_points") if isinstance(data, dict) else None
    if not isinstance(reference_set, dict) or not isinstance(spectrum_points, list):
        raise HTTPException(status_code=422, detail={"code": "invalid_reference_set_package", "message": "Hiányzó reference_set vagy spectrum_points."})
    request = ReferenceSetCaptureRequest(
        name=str(reference_set.get("name") or filename),
        reference_key=str(reference_set.get("reference_key") or Path(filename).stem),
        location_name=str(reference_set.get("location_name") or "imported"),
        measurement_session_id=None,
        operator_name=reference_set.get("created_by"),
        notes=reference_set.get("notes"),
        spectrum_reference_kind=str((data.get("spectrum_reference") or {}).get("reference_kind") or "imported").replace("imported", "snapshot"),
        spectrum_points=spectrum_points,
        spectrum_metadata={"imported_from": filename},
        include_wifi=False,
        include_bluetooth=False,
        activate=activate,
    )
    return capture_reference_set(request)


@router.get("/api/reference-sets/{reference_set_id}/compare/wifi")
def compare_reference_set_wifi(reference_set_id: str, measurement_session_id: str | None = None):
    identifier = validated_optional_uuid(reference_set_id, "reference_set_id")
    session_id = validated_optional_uuid(measurement_session_id, "measurement_session_id") if measurement_session_id else None
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT location_name FROM reference_sets WHERE id=%s", (identifier,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="reference_set_not_found")
            return compute_baseline_comparison(
                cur,
                protocol="wifi",
                location_name=row["location_name"],
                session_id=session_id,
                grace_seconds=_baseline_grace("wifi"),
                reference_set_id=identifier,
            )


@router.get("/api/reference-sets/{reference_set_id}/compare/bluetooth")
def compare_reference_set_bluetooth(reference_set_id: str, measurement_session_id: str | None = None):
    identifier = validated_optional_uuid(reference_set_id, "reference_set_id")
    session_id = validated_optional_uuid(measurement_session_id, "measurement_session_id") if measurement_session_id else None
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT location_name FROM reference_sets WHERE id=%s", (identifier,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="reference_set_not_found")
            return compute_baseline_comparison(
                cur,
                protocol="bluetooth",
                location_name=row["location_name"],
                session_id=session_id,
                grace_seconds=_baseline_grace("bluetooth"),
                reference_set_id=identifier,
            )
