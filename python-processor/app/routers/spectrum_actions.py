from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from psycopg.types.json import Jsonb

from app.db import get_db
from app.schemas import PeakSaveRequest, ReferenceCaptureRequest
from app.services.csv_export import csv_export_response
from app.services.persistence import ensure_location

router = APIRouter()
REFERENCE_KEY_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,128}")

_SPECTRUM_PEAK_FIELDS = [
    "id", "time", "session_id", "session_title", "location_name",
    "peak_type", "frequency_hz", "power_dbm", "metadata",
]

@router.post("/api/spectrum/reference-captures")
def save_reference_capture(request: ReferenceCaptureRequest):
    if not request.points:
        raise HTTPException(status_code=400, detail="Nincs mentheto spektrum pont.")
    if len(request.points) > 25000:
        raise HTTPException(status_code=400, detail="Tul sok spektrum pont egy mentésben.")

    captured_at = datetime.now(timezone.utc)
    reference_key = request.reference_id.strip()
    if not REFERENCE_KEY_PATTERN.fullmatch(reference_key):
        raise HTTPException(status_code=422, detail="Érvénytelen referencia azonosító.")
    normalized_points: list[tuple[int, float]] = []
    for point in request.points:
        frequency_hz = point.frequency_hz
        if frequency_hz is None and point.frequency_mhz is not None:
            frequency_hz = int(point.frequency_mhz * 1_000_000)
        if frequency_hz is None:
            continue
        normalized_points.append((int(frequency_hz), float(point.power_dbm)))
    normalized_points.sort(key=lambda item: item[0])
    if not normalized_points:
        raise HTTPException(status_code=400, detail="Nincs mentheto spektrum pont.")
    frequencies = [item[0] for item in normalized_points]
    differences = {frequencies[index] - frequencies[index - 1] for index in range(1, len(frequencies))}
    step = next(iter(differences)) if len(differences) == 1 else None
    checksum_payload = json.dumps(normalized_points, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    checksum = hashlib.sha256(checksum_payload).hexdigest()
    inserted = 0
    with get_db() as conn:
        with conn.cursor() as cur:
            location_id = ensure_location(cur, request.location_name)
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (reference_key,))
            cur.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS version FROM spectrum_references WHERE reference_key=%s",
                (reference_key,),
            )
            version = cur.fetchone()["version"]
            cur.execute(
                "UPDATE spectrum_references SET is_active=false, updated_at=now() "
                "WHERE reference_key=%s AND archived_at IS NULL",
                (reference_key,),
            )
            cur.execute(
                """
                INSERT INTO spectrum_references
                  (reference_key, version, location_id, location_name, device_name, source_type,
                   antenna, downconverter_profile, start_frequency_hz, stop_frequency_hz,
                   step_frequency_hz, rbw_hz, vbw_hz, measured_at, notes,
                   checksum_sha256, is_active, creation_source, original_filename,
                   import_format, point_count, metadata)
                VALUES
                  (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,'live',%s,'live_spectrum_capture',%s,%s)
                RETURNING id
                """,
                (
                    reference_key,
                    version,
                    location_id,
                    request.location_name,
                    request.device_name,
                    "spectrum_monitor",
                    request.antenna,
                    request.downconverter_profile,
                    frequencies[0],
                    frequencies[-1],
                    step,
                    request.rbw_hz,
                    request.vbw_hz,
                    captured_at,
                    "Live spectrum monitor reference capture.",
                    checksum,
                    request.source_file,
                    len(normalized_points),
                    Jsonb({"layer_type": "reference", "display_color": "#ff5252", "source": "live_spectrum_capture"}),
                ),
            )
            reference_uuid = str(cur.fetchone()["id"])
            for frequency_hz, power_dbm in normalized_points:
                cur.execute(
                    """
                    INSERT INTO reference_spectrum_points
                      (time, reference_id, location_id, location_name, device_name, source_file,
                       measured_frequency_hz, actual_rf_frequency_hz, power_dbm,
                       rbw_hz, vbw_hz, antenna, downconverter_profile, raw_row)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        captured_at,
                        reference_uuid,
                        location_id,
                        request.location_name,
                        request.device_name,
                        request.source_file,
                        frequency_hz,
                        frequency_hz,
                        power_dbm,
                        request.rbw_hz,
                        request.vbw_hz,
                        request.antenna,
                        request.downconverter_profile,
                        Jsonb({
                            "source": "live_spectrum_capture",
                            "reference_key": reference_key,
                            "reference_version": version,
                            "layer_type": "reference",
                            "display_color": "#ff5252",
                        }),
                    ),
                )
                inserted += 1
        conn.commit()
    return {
        "id": reference_uuid,
        "reference_id": reference_uuid,
        "reference_key": reference_key,
        "version": version,
        "location_name": request.location_name,
        "inserted_points": inserted,
        "captured_at": captured_at.isoformat(),
    }


@router.post("/api/spectrum/peaks")
def save_spectrum_peak(request: PeakSaveRequest):
    frequency_hz = request.frequency_hz
    if frequency_hz is None and request.frequency_mhz is not None:
        frequency_hz = int(request.frequency_mhz * 1_000_000)
    if frequency_hz is None:
        raise HTTPException(status_code=400, detail="Frekvencia hianyzik.")

    now = datetime.now(timezone.utc)
    with get_db() as conn:
        with conn.cursor() as cur:
            location_id = ensure_location(cur, request.location_name)
            cur.execute(
                """
                SELECT id
                FROM measurement_sessions
                WHERE lower(location_name) = lower(%s)
                  AND status = 'active'
                  AND ended_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (request.location_name.strip(),),
            )
            active_session = cur.fetchone()
            if active_session:
                session_id = str(active_session["id"])
            else:
                cur.execute(
                    """
                    INSERT INTO measurement_sessions
                      (location_id, location_name, started_at, ended_at, mode,
                       title, notes, status, metadata, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, 'spectrum_peak', %s, %s,
                            'stopped', %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        location_id,
                        request.location_name.strip(),
                        now,
                        now,
                        request.session_title or "Manual spectrum peak save",
                        "Automatically closed one-shot session for manual peak save.",
                        Jsonb(request.metadata or {}),
                        now,
                        now,
                    ),
                )
                session_id = str(cur.fetchone()["id"])
            cur.execute(
                """
                INSERT INTO spectrum_peaks
                  (time, session_id, location_id, peak_type, frequency_hz, power_dbm, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    now,
                    session_id,
                    location_id,
                    request.peak_type,
                    frequency_hz,
                    request.power_dbm,
                    Jsonb(request.metadata or {}),
                ),
            )
            peak_id = str(cur.fetchone()["id"])
        conn.commit()
    return {
        "id": peak_id,
        "session_id": session_id,
        "location_name": request.location_name,
        "frequency_hz": frequency_hz,
        "power_dbm": request.power_dbm,
    }


def _spectrum_peaks_query(
    location_name: str | None, start_time: datetime | None, end_time: datetime | None,
) -> tuple[str, list]:
    conditions: list[str] = []
    parameters: list = []
    if location_name and location_name.strip():
        conditions.append("lower(l.name) = lower(%s)")
        parameters.append(location_name.strip())
    if start_time:
        conditions.append("p.time >= %s")
        parameters.append(start_time)
    if end_time:
        conditions.append("p.time <= %s")
        parameters.append(end_time)
    where_sql = " WHERE " + " AND ".join(conditions) if conditions else ""
    query = (
        """
        SELECT p.id, p.time, p.session_id, s.title AS session_title, l.name AS location_name,
               p.peak_type, p.frequency_hz, p.power_dbm, p.metadata
        FROM spectrum_peaks p
        LEFT JOIN locations l ON l.id = p.location_id
        LEFT JOIN measurement_sessions s ON s.id = p.session_id
        """
        + where_sql
        + " ORDER BY p.time DESC"
    )
    return query, parameters


@router.get("/api/spectrum/peaks")
def list_spectrum_peaks(
    location_name: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 200,
):
    safe_limit = max(1, min(limit, 5000))
    query, parameters = _spectrum_peaks_query(location_name, start_time, end_time)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query + " LIMIT %s", (*parameters, safe_limit))
            items = list(cur.fetchall())
    return {"items": items, "limit": safe_limit}


@router.get("/api/spectrum/peaks/export")
def export_spectrum_peaks(
    location_name: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
):
    query, parameters = _spectrum_peaks_query(location_name, start_time, end_time)

    def rows():
        with get_db() as conn:
            with conn.cursor(name="spectrum_peaks_export") as cur:
                cur.itersize = 2000
                cur.execute(query, parameters)
                yield from cur

    return csv_export_response("spectrum_peaks.csv", _SPECTRUM_PEAK_FIELDS, rows())
