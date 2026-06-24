from __future__ import annotations

import asyncio
import hashlib
import os
from typing import Any

from psycopg.types.json import Jsonb

from app.db import get_db
from app.services.known_signals import evaluate_known_signal

from .pipeline import SpectrumEnvelope
from .spectrum import Detection

_SEVERITY_TO_ALERT = {
    "info": "info",
    "low": "info",
    "medium": "warning",
    "high": "error",
    "critical": "critical",
}
_ALERT_THRESHOLD = os.getenv("ANOMALY_ALERT_MIN_SEVERITY", "high").strip().lower()
_SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _deduplication_key(detection: Detection) -> str:
    frequency = detection.center_frequency_hz or detection.start_frequency_hz or 0
    bandwidth = max(detection.bandwidth_hz or 1, 1)
    bucket = int(round(frequency / bandwidth)) if frequency else 0
    raw = f"{detection.entity_domain}:{detection.class_name}:{bucket}:{bandwidth}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_known_signal_profiles(cur, detection: Detection) -> list[dict[str, Any]]:
    if not detection.center_frequency_hz:
        return []
    cur.execute(
        """
        SELECT * FROM known_signals
        WHERE archived_at IS NULL AND status = 'active'
          AND (valid_from IS NULL OR valid_from <= now())
          AND (valid_until IS NULL OR valid_until > now())
          AND abs(center_frequency_hz - %s) <= frequency_tolerance_hz
        ORDER BY abs(center_frequency_hz - %s), updated_at DESC
        LIMIT 20
        """,
        (detection.center_frequency_hz, detection.center_frequency_hz),
    )
    return list(cur.fetchall())


def _persist_sync(envelope: SpectrumEnvelope, detections: list[Detection]) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            for detection in detections:
                known_signal_id = None
                disposition = "new"
                suppression_reason = None
                matches: list[dict[str, Any]] = []
                measurement = {
                    "center_frequency_hz": detection.center_frequency_hz or detection.start_frequency_hz,
                    "bandwidth_hz": detection.bandwidth_hz,
                    "power_dbm": detection.power_dbm,
                    "source_type": envelope.source_type,
                }
                if measurement["center_frequency_hz"]:
                    for profile in _load_known_signal_profiles(cur, detection):
                        match = evaluate_known_signal(profile, measurement)
                        matches.append(match)
                        if match["matched"]:
                            known_signal_id = match["known_signal_id"]
                            disposition = "known"
                            if match["suppress_alert"]:
                                suppression_reason = match["suppression_reason"]
                            break
                metadata = {
                    "source_type": envelope.source_type,
                    "sequence": envelope.sequence,
                    "center_frequency_hz": detection.center_frequency_hz,
                    "power_dbm": detection.power_dbm,
                    "bandwidth_hz": detection.bandwidth_hz,
                    "known_signal_matches": matches,
                }
                cur.execute(
                    """
                    INSERT INTO rf_detections
                      (detected_at, measurement_session_id, recording_id, source_type,
                       model_name, model_version, class_name, confidence,
                       start_frequency_hz, stop_frequency_hz, known_signal_id,
                       disposition, suppression_reason, metadata, entity_domain,
                       detector_name, detector_version, severity, explanation, evidence)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                    """,
                    (
                        detection.detected_at,
                        envelope.measurement_session_id,
                        envelope.recording_id,
                        envelope.source_type,
                        detection.detector_name,
                        detection.detector_version,
                        detection.class_name,
                        detection.confidence,
                        detection.start_frequency_hz,
                        detection.stop_frequency_hz,
                        known_signal_id,
                        disposition,
                        suppression_reason,
                        Jsonb(metadata),
                        detection.entity_domain,
                        detection.detector_name,
                        detection.detector_version,
                        detection.severity,
                        detection.explanation,
                        Jsonb(detection.evidence),
                    ),
                )
                detection_id = str(cur.fetchone()["id"])
                if (
                    suppression_reason is None
                    and _SEVERITY_RANK.get(detection.severity, 0)
                    >= _SEVERITY_RANK.get(_ALERT_THRESHOLD, 3)
                ):
                    alert_severity = _SEVERITY_TO_ALERT.get(detection.severity, "warning")
                    domain = {
                        "spectrum": "rf_security",
                        "wifi": "wifi_security",
                        "bluetooth": "bluetooth_security",
                        "technical": "technical",
                    }.get(detection.entity_domain, "technical")
                    dedup = _deduplication_key(detection)
                    cur.execute(
                        """
                        INSERT INTO system_alerts
                          (severity, status, source, code, message, entity_type, entity_id,
                           metadata, domain, deduplication_key, occurrence_count,
                           last_seen_at, rf_detection_id, measurement_session_id, updated_at)
                        VALUES (%s,'open','anomaly_pipeline',%s,%s,'rf_detection',%s,%s,%s,%s,1,now(),%s,%s,now())
                        ON CONFLICT (deduplication_key)
                          WHERE deduplication_key IS NOT NULL AND status IN ('open','acknowledged')
                        DO UPDATE SET
                          occurrence_count = system_alerts.occurrence_count + 1,
                          last_seen_at = now(),
                          severity = EXCLUDED.severity,
                          message = EXCLUDED.message,
                          metadata = system_alerts.metadata || EXCLUDED.metadata,
                          rf_detection_id = EXCLUDED.rf_detection_id,
                          updated_at = now()
                        """,
                        (
                            alert_severity,
                            detection.class_name,
                            detection.explanation,
                            detection_id,
                            Jsonb({"evidence": detection.evidence, "confidence": detection.confidence}),
                            domain,
                            dedup,
                            detection_id,
                            envelope.measurement_session_id,
                        ),
                    )
        conn.commit()


async def persist_detection_batch(envelope: SpectrumEnvelope, detections: list[Detection]) -> None:
    await asyncio.to_thread(_persist_sync, envelope, detections)
