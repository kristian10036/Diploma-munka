from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.db import _validated_optional_uuid, _write_audit_event, get_db
from app.metrics import (
    ALERTS_OPEN,
    ANOMALY_QUEUE_DEPTH,
    ANOMALY_QUEUE_DROPS,
)
from app.runtime import ANOMALY_PIPELINE
from app.schemas import AlertAcknowledgeRequest, AlertResolveRequest, DetectionReviewRequest
from app.services.anomaly import detect_bluetooth_anomalies, detect_wifi_anomalies
from app.utils.pagination import decode_time_uuid_cursor, encode_time_uuid_cursor

router = APIRouter()


@router.get("/api/anomalies/status")
def anomaly_status():
    status = ANOMALY_PIPELINE.status()
    ANOMALY_QUEUE_DEPTH.set(status["queue_depth"])
    ANOMALY_QUEUE_DROPS.set(status["dropped_frames"])
    return status


@router.get("/api/anomalies/recent")
def recent_anomalies(limit: int = Query(default=100, ge=1, le=500), domain: str | None = None):
    items = list(ANOMALY_PIPELINE.recent)
    if domain:
        items = [item for item in items if item.get("entity_domain") == domain]
    return {"items": items[:limit], "count": min(len(items), limit), "persistence": "best_effort_database"}


@router.post("/api/anomalies/evaluate/wifi")
def evaluate_wifi_anomaly(payload: dict[str, Any]):
    current = payload.get("current")
    history = payload.get("history", [])
    if not isinstance(current, dict) or not isinstance(history, list):
        raise HTTPException(status_code=422, detail="current_object_and_history_array_required")
    items = [item.as_dict() for item in detect_wifi_anomalies(current, history)]
    return {"items": items, "count": len(items), "persisted": False}


@router.post("/api/anomalies/evaluate/bluetooth")
def evaluate_bluetooth_anomaly(payload: dict[str, Any]):
    current = payload.get("current")
    history = payload.get("history", [])
    if not isinstance(current, dict) or not isinstance(history, list):
        raise HTTPException(status_code=422, detail="current_object_and_history_array_required")
    items = [item.as_dict() for item in detect_bluetooth_anomalies(current, history)]
    return {"items": items, "count": len(items), "persisted": False,
            "identity_warning": "Randomized BLE addresses are not treated as certain identity."}


@router.get("/api/detections")
def list_detections(
    limit: int = Query(default=100, ge=1, le=500),
    domain: str | None = None,
    disposition: str | None = None,
    severity: str | None = None,
    cursor: str | None = None,
    measurement_session_id: uuid.UUID | None = None,
):
    clauses: list[str] = []
    values: list[Any] = []
    if measurement_session_id:
        clauses.append("measurement_session_id = %s"); values.append(measurement_session_id)
    if domain:
        if domain not in {"spectrum", "wifi", "bluetooth", "technical"}:
            raise HTTPException(status_code=422, detail="invalid_detection_domain")
        clauses.append("entity_domain = %s"); values.append(domain)
    if disposition:
        if disposition not in {"new", "known", "changed", "false_positive", "reviewed"}:
            raise HTTPException(status_code=422, detail="invalid_detection_disposition")
        clauses.append("disposition = %s"); values.append(disposition)
    if severity:
        if severity not in {"info", "low", "medium", "high", "critical"}:
            raise HTTPException(status_code=422, detail="invalid_detection_severity")
        clauses.append("severity = %s"); values.append(severity)
    if cursor:
        try:
            cursor_time, cursor_id = decode_time_uuid_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid_pagination_cursor") from exc
        clauses.append("(detected_at, id) < (%s, %s)")
        values.extend((cursor_time, cursor_id))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM rf_detections{where} ORDER BY detected_at DESC, id DESC LIMIT %s",
                (*values, limit + 1),
            )
            fetched = list(cur.fetchall())
    has_more = len(fetched) > limit
    rows = fetched[:limit]
    next_cursor = None
    if has_more and rows:
        next_cursor = encode_time_uuid_cursor(rows[-1]["detected_at"], rows[-1]["id"])
    return {"items": rows, "count": len(rows), "has_more": has_more, "next_cursor": next_cursor}


@router.patch("/api/detections/{detection_id}/review")
def review_detection(detection_id: str, request: DetectionReviewRequest):
    detection_uuid = _validated_optional_uuid(detection_id, "detection_id")
    if request.disposition not in {"known", "changed", "false_positive", "reviewed"}:
        raise HTTPException(status_code=422, detail="invalid_detection_disposition")
    known_signal_id = _validated_optional_uuid(request.known_signal_id, "known_signal_id")
    operator = (request.reviewed_by or "operator").strip()[:200]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE rf_detections SET
                  disposition=%s, review_notes=%s, known_signal_id=%s,
                  reviewed_at=now(), reviewed_by=%s, include_in_training=%s,
                  updated_at=now()
                WHERE id=%s RETURNING *
                """,
                (request.disposition, request.review_notes, known_signal_id, operator,
                 request.include_in_training, detection_uuid),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail="detection_not_found")
    _write_audit_event(
        "rf_detection.reviewed", entity_type="rf_detection", entity_id=detection_uuid,
        actor=operator, details={"disposition": request.disposition,
                                 "include_in_training": request.include_in_training,
                                 "known_signal_id": known_signal_id},
    )
    return row


@router.get("/api/alerts")
def list_alerts(
    limit: int = Query(default=100, ge=1, le=500),
    status: str | None = None,
    domain: str | None = None,
    severity: str | None = None,
    cursor: str | None = None,
    measurement_session_id: uuid.UUID | None = None,
):
    clauses: list[str] = []
    values: list[Any] = []
    if measurement_session_id:
        clauses.append("measurement_session_id = %s"); values.append(measurement_session_id)
    if status:
        if status not in {"open", "acknowledged", "resolved"}:
            raise HTTPException(status_code=422, detail="invalid_alert_status")
        clauses.append("status = %s"); values.append(status)
    if domain:
        if domain not in {"technical", "rf_security", "wifi_security", "bluetooth_security"}:
            raise HTTPException(status_code=422, detail="invalid_alert_domain")
        clauses.append("domain = %s"); values.append(domain)
    if severity:
        if severity not in {"info", "warning", "error", "critical"}:
            raise HTTPException(status_code=422, detail="invalid_alert_severity")
        clauses.append("severity = %s"); values.append(severity)
    if cursor:
        try:
            cursor_time, cursor_id = decode_time_uuid_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid_pagination_cursor") from exc
        clauses.append("(last_seen_at, id) < (%s, %s)")
        values.extend((cursor_time, cursor_id))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM system_alerts{where} ORDER BY last_seen_at DESC, id DESC LIMIT %s",
                (*values, limit + 1),
            )
            fetched = list(cur.fetchall())
            cur.execute("SELECT severity, count(*) AS count FROM system_alerts WHERE status <> 'resolved' GROUP BY severity")
            counts = list(cur.fetchall())
    has_more = len(fetched) > limit
    rows = fetched[:limit]
    next_cursor = None
    if has_more and rows:
        next_cursor = encode_time_uuid_cursor(rows[-1]["last_seen_at"], rows[-1]["id"])
    for item in counts:
        ALERTS_OPEN.labels(severity=item["severity"]).set(item["count"])
    return {"items": rows, "count": len(rows), "has_more": has_more, "next_cursor": next_cursor}


def _event_metadata_value(metadata: dict[str, Any] | None, *keys: str) -> Any:
    if not isinstance(metadata, dict):
        return None
    evidence = metadata.get("evidence")
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return value
        if isinstance(evidence, dict):
            value = evidence.get(key)
            if value not in (None, ""):
                return value
    return None


def _wifi_security_event(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    timestamp = row.get("last_seen_at") or row.get("created_at")
    description = _event_metadata_value(metadata, "description", "explanation") or row.get("message")
    confidence = _event_metadata_value(metadata, "confidence")
    return {
        "id": row.get("id"),
        "timestamp": timestamp,
        "alert_type": row.get("code"),
        "severity": row.get("severity"),
        "status": row.get("status"),
        "source": row.get("source"),
        "transmitter_label": "Feltételezett keretküldő",
        "suspected_transmitter_mac": _event_metadata_value(
            metadata,
            "suspected_transmitter_mac",
            "transmitter_mac",
            "source_mac",
            "src_mac",
        ),
        "destination_mac": _event_metadata_value(
            metadata,
            "destination_mac",
            "victim_mac",
            "dst_mac",
        ),
        "bssid": _event_metadata_value(metadata, "bssid"),
        "ssid": _event_metadata_value(metadata, "ssid"),
        "frame_type": _event_metadata_value(metadata, "frame_type", "management_frame_type"),
        "reason_code": _event_metadata_value(metadata, "reason_code"),
        "channel": _event_metadata_value(metadata, "channel"),
        "frequency_hz": _event_metadata_value(metadata, "frequency_hz"),
        "rssi_dbm": _event_metadata_value(metadata, "rssi_dbm", "signal_dbm"),
        "event_count": row.get("occurrence_count") or _event_metadata_value(metadata, "event_count"),
        "description": description,
        "confidence": confidence,
        "review_state": row.get("status"),
        "metadata": metadata,
    }


@router.get("/api/wifi/security-events")
def list_wifi_security_events(
    limit: int = Query(default=100, ge=1, le=500),
    status: str | None = None,
    severity: str | None = None,
    cursor: str | None = None,
    measurement_session_id: uuid.UUID | None = None,
):
    clauses = ["domain = 'wifi_security'"]
    values: list[Any] = []
    if measurement_session_id:
        clauses.append("measurement_session_id = %s"); values.append(measurement_session_id)
    if status:
        if status not in {"open", "acknowledged", "resolved"}:
            raise HTTPException(status_code=422, detail="invalid_alert_status")
        clauses.append("status = %s"); values.append(status)
    if severity:
        if severity not in {"info", "warning", "error", "critical"}:
            raise HTTPException(status_code=422, detail="invalid_alert_severity")
        clauses.append("severity = %s"); values.append(severity)
    if cursor:
        try:
            cursor_time, cursor_id = decode_time_uuid_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid_pagination_cursor") from exc
        clauses.append("(last_seen_at, id) < (%s, %s)")
        values.extend((cursor_time, cursor_id))
    where = " WHERE " + " AND ".join(clauses)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM system_alerts{where} ORDER BY last_seen_at DESC, id DESC LIMIT %s",
                (*values, limit + 1),
            )
            fetched = list(cur.fetchall())
    has_more = len(fetched) > limit
    rows = fetched[:limit]
    next_cursor = None
    if has_more and rows:
        next_cursor = encode_time_uuid_cursor(rows[-1]["last_seen_at"], rows[-1]["id"])
    return {
        "items": [_wifi_security_event(row) for row in rows],
        "count": len(rows),
        "has_more": has_more,
        "next_cursor": next_cursor,
        "transmitter_label": "Feltételezett keretküldő",
    }


def _update_alert(alert_id: str, *, target_status: str, operator: str, note: str | None) -> dict[str, Any]:
    alert_uuid = _validated_optional_uuid(alert_id, "alert_id")
    if target_status == "acknowledged":
        assignments = "status='acknowledged', acknowledged_at=now(), acknowledged_by=%s, acknowledgement_note=%s, updated_at=now()"
    elif target_status == "resolved":
        assignments = "status='resolved', resolved_at=now(), resolved_by=%s, resolution_note=%s, updated_at=now()"
    else:
        raise ValueError("unsupported alert transition")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE system_alerts SET {assignments} WHERE id=%s AND status <> 'resolved' RETURNING *", (operator, note, alert_uuid))
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail="alert_not_found_or_already_resolved")
    _write_audit_event(f"system_alert.{target_status}", entity_type="system_alert", entity_id=alert_uuid,
                       actor=operator, details={"note": note})
    return row


@router.post("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str, request: AlertAcknowledgeRequest):
    return _update_alert(alert_id, target_status="acknowledged",
                         operator=request.operator.strip()[:200], note=request.note)


@router.post("/api/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: str, request: AlertResolveRequest):
    return _update_alert(alert_id, target_status="resolved",
                         operator=request.operator.strip()[:200], note=request.note)
