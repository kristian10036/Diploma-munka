from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from psycopg import sql
from psycopg.types.json import Jsonb

from app.db import _validated_optional_uuid, _write_audit_event, get_db
from app.schemas import (KnownSignalMatchRequest, KnownSignalRequest, KnownSignalUpdate,
    SpectrumMarkerRequest, SpectrumMarkerUpdate)
from app.services.known_signals import evaluate_known_signal
from app.services.persistence import fetch_repeated_macs

router = APIRouter()

@router.get("/api/analysis/repeated-macs")
def repeated_macs(min_locations: int = 2):
    return {"items": fetch_repeated_macs(max(2, min_locations))}


@router.get("/api/markers")
def list_spectrum_markers(limit: int = 100, measurement_session_id: str | None = None, include_archived: bool = False):
    bounded_limit = min(max(limit, 1), 500)
    session_id = _validated_optional_uuid(measurement_session_id, "measurement_session_id")
    with get_db() as conn:
        with conn.cursor() as cur:
            clauses, values = [], []
            if session_id:
                clauses.append("measurement_session_id = %s")
                values.append(session_id)
            if not include_archived:
                clauses.append("archived_at IS NULL")
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            cur.execute(f"SELECT * FROM spectrum_markers{where} ORDER BY created_at DESC LIMIT %s", (*values, bounded_limit))
            rows = cur.fetchall()
    return {"items": rows, "count": len(rows)}


@router.post("/api/markers")
def create_spectrum_marker(request: SpectrumMarkerRequest):
    if request.frequency_hz <= 0:
        raise HTTPException(status_code=422, detail="invalid_frequency_hz")
    label = request.label.strip()
    if not label or len(label) > 200:
        raise HTTPException(status_code=422, detail="invalid_label")
    session_id = _validated_optional_uuid(request.measurement_session_id, "measurement_session_id")
    location_id = _validated_optional_uuid(request.location_id, "location_id")
    recording_id = request.recording_id.strip() if request.recording_id else None
    if recording_id and not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", recording_id):
        raise HTTPException(status_code=422, detail="invalid_recording_id")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO spectrum_markers
                  (location_id, measurement_session_id, recording_id, frequency_hz, power_dbm,
                   label, notes, category, color, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    location_id, session_id, recording_id, request.frequency_hz, request.power_dbm,
                    label, request.notes, request.category, request.color, Jsonb(request.metadata or {}),
                ),
            )
            row = cur.fetchone()
        conn.commit()
    _write_audit_event(
        "spectrum.marker.created",
        entity_type="spectrum_marker",
        entity_id=str(row["id"]),
        details={"frequency_hz": request.frequency_hz, "recording_id": recording_id},
    )
    return row


@router.get("/api/markers/{marker_id}")
def get_spectrum_marker(marker_id: str):
    marker_uuid = _validated_optional_uuid(marker_id, "marker_id")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM spectrum_markers WHERE id = %s", (marker_uuid,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="marker_not_found")
    return row


@router.patch("/api/markers/{marker_id}")
def update_spectrum_marker(marker_id: str, request: SpectrumMarkerUpdate):
    marker_uuid = _validated_optional_uuid(marker_id, "marker_id")
    changes = request.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="empty_update")
    for field in ("location_id", "measurement_session_id"):
        if field in changes:
            changes[field] = _validated_optional_uuid(changes[field], field)
    if "frequency_hz" in changes and (changes["frequency_hz"] is None or changes["frequency_hz"] <= 0):
        raise HTTPException(status_code=422, detail="invalid_frequency_hz")
    if "label" in changes and (changes["label"] is None or not changes["label"].strip()):
        raise HTTPException(status_code=422, detail="invalid_label")
    if "metadata" in changes:
        changes["metadata"] = Jsonb(changes["metadata"] or {})
    assignments = [sql.SQL("{} = %s").format(sql.Identifier(field)) for field in changes]
    query = sql.SQL("UPDATE spectrum_markers SET {}, updated_at = now() WHERE id = %s RETURNING *").format(sql.SQL(", ").join(assignments))
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (*changes.values(), marker_uuid))
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail="marker_not_found")
    _write_audit_event("spectrum.marker.updated", entity_type="spectrum_marker", entity_id=marker_uuid, details={"fields": list(changes)})
    return row


@router.delete("/api/markers/{marker_id}")
def archive_spectrum_marker(marker_id: str):
    marker_uuid = _validated_optional_uuid(marker_id, "marker_id")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE spectrum_markers SET archived_at = now(), updated_at = now() WHERE id = %s AND archived_at IS NULL RETURNING *", (marker_uuid,))
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail="marker_not_found_or_archived")
    _write_audit_event("spectrum.marker.archived", entity_type="spectrum_marker", entity_id=marker_uuid)
    return row


def _validate_known_signal(request: KnownSignalRequest | KnownSignalUpdate) -> None:
    values = request.model_dump(exclude_unset=True)
    if values.get("center_frequency_hz", 1) <= 0 or values.get("frequency_tolerance_hz", 1) <= 0:
        raise HTTPException(status_code=422, detail="invalid_known_signal_frequency")
    if values.get("status", "active") not in {"active", "disabled", "expired"}:
        raise HTTPException(status_code=422, detail="invalid_known_signal_status")
    if "label" in values and (values["label"] is None or not values["label"].strip() or len(values["label"]) > 200):
        raise HTTPException(status_code=422, detail="invalid_known_signal_label")
    low, high = values.get("expected_power_min_dbm"), values.get("expected_power_max_dbm")
    if low is not None and high is not None and low > high:
        raise HTTPException(status_code=422, detail="invalid_known_signal_power_range")


@router.get("/api/known-signals")
def list_known_signals(limit: int = 100, status: str | None = None, include_archived: bool = False):
    bounded_limit = min(max(limit, 1), 500)
    clauses, values = [], []
    if status:
        if status not in {"active", "disabled", "expired"}:
            raise HTTPException(status_code=422, detail="invalid_known_signal_status")
        clauses.append("status = %s"); values.append(status)
    if not include_archived:
        clauses.append("archived_at IS NULL")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM known_signals{where} ORDER BY updated_at DESC LIMIT %s", (*values, bounded_limit))
            rows = cur.fetchall()
    return {"items": rows, "count": len(rows)}


@router.post("/api/known-signals", status_code=201)
def create_known_signal(request: KnownSignalRequest):
    _validate_known_signal(request)
    location_id = _validated_optional_uuid(request.location_id, "location_id")
    session_id = _validated_optional_uuid(request.measurement_session_id, "measurement_session_id")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO known_signals
                  (location_id, measurement_session_id, center_frequency_hz, frequency_tolerance_hz,
                   bandwidth_hz, expected_power_min_dbm, expected_power_max_dbm, modulation, protocol,
                   source_type, label, notes, status, suppress_alerts, valid_from, valid_until, metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
            """, (location_id, session_id, request.center_frequency_hz, request.frequency_tolerance_hz,
                   request.bandwidth_hz, request.expected_power_min_dbm, request.expected_power_max_dbm,
                   request.modulation, request.protocol, request.source_type, request.label.strip(), request.notes,
                   request.status, request.suppress_alerts, request.valid_from, request.valid_until, Jsonb(request.metadata or {})))
            row = cur.fetchone()
        conn.commit()
    _write_audit_event("spectrum.known_signal.created", entity_type="known_signal", entity_id=str(row["id"]), details={"center_frequency_hz": request.center_frequency_hz})
    return row


@router.get("/api/known-signals/{known_signal_id}")
def get_known_signal(known_signal_id: str):
    signal_uuid = _validated_optional_uuid(known_signal_id, "known_signal_id")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM known_signals WHERE id = %s", (signal_uuid,)); row = cur.fetchone()
    if not row: raise HTTPException(status_code=404, detail="known_signal_not_found")
    return row


@router.patch("/api/known-signals/{known_signal_id}")
def update_known_signal(known_signal_id: str, request: KnownSignalUpdate):
    signal_uuid = _validated_optional_uuid(known_signal_id, "known_signal_id")
    _validate_known_signal(request)
    changes = request.model_dump(exclude_unset=True)
    if not changes: raise HTTPException(status_code=422, detail="empty_update")
    if "metadata" in changes: changes["metadata"] = Jsonb(changes["metadata"] or {})
    assignments = [sql.SQL("{} = %s").format(sql.Identifier(field)) for field in changes]
    query = sql.SQL("UPDATE known_signals SET {}, updated_at = now() WHERE id = %s RETURNING *").format(sql.SQL(", ").join(assignments))
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (*changes.values(), signal_uuid)); row = cur.fetchone()
        conn.commit()
    if not row: raise HTTPException(status_code=404, detail="known_signal_not_found")
    _write_audit_event("spectrum.known_signal.updated", entity_type="known_signal", entity_id=signal_uuid, details={"fields": list(changes)})
    return row


@router.delete("/api/known-signals/{known_signal_id}")
def archive_known_signal(known_signal_id: str):
    signal_uuid = _validated_optional_uuid(known_signal_id, "known_signal_id")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE known_signals SET archived_at=now(), status='disabled', updated_at=now() WHERE id=%s AND archived_at IS NULL RETURNING *", (signal_uuid,)); row=cur.fetchone()
        conn.commit()
    if not row: raise HTTPException(status_code=404, detail="known_signal_not_found_or_archived")
    _write_audit_event("spectrum.known_signal.archived", entity_type="known_signal", entity_id=signal_uuid)
    return row


@router.post("/api/known-signals/match")
def match_known_signal(request: KnownSignalMatchRequest):
    location_id = _validated_optional_uuid(request.location_id, "location_id")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT * FROM known_signals
                WHERE archived_at IS NULL AND status='active'
                  AND (valid_from IS NULL OR valid_from <= now()) AND (valid_until IS NULL OR valid_until > now())
                  AND abs(center_frequency_hz - %s) <= frequency_tolerance_hz
                  AND (location_id IS NULL OR location_id = %s)
                ORDER BY abs(center_frequency_hz - %s), updated_at DESC LIMIT 20""",
                (request.center_frequency_hz, location_id, request.center_frequency_hz))
            profiles = cur.fetchall()
    measurement = request.model_dump()
    matches = [evaluate_known_signal(profile, measurement) | {"label": profile["label"]} for profile in profiles]
    return {"matches": matches, "matched": any(item["matched"] for item in matches),
            "suppress_alert": any(item["suppress_alert"] for item in matches)}


@router.get("/api/audit/events")
def list_audit_events(limit: int = 100, event_type: str | None = None):
    bounded_limit = min(max(limit, 1), 500)
    with get_db() as conn:
        with conn.cursor() as cur:
            if event_type:
                cur.execute(
                    "SELECT * FROM audit_events WHERE event_type = %s ORDER BY occurred_at DESC LIMIT %s",
                    (event_type, bounded_limit),
                )
            else:
                cur.execute(
                    "SELECT * FROM audit_events ORDER BY occurred_at DESC LIMIT %s",
                    (bounded_limit,),
                )
            rows = cur.fetchall()
    return {"items": rows, "count": len(rows)}
