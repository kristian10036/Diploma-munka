from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from psycopg.types.json import Jsonb

from app.db import get_db
from app.runtime import DEVICE_IMPORT_TABLES
from app.schemas import MeasurementSourceRequest, SessionStartRequest
from app.runtime import SINGLE_ACTIVE_MEASUREMENT_SESSION
from app.services.persistence import (create_csv_import, ensure_bettercap_measurement_source,
    ensure_kismet_measurement_source, ensure_location, extract_common_fields, insert_device_import_row,
    resolve_import_session, save_uploaded_file, upsert_bluetooth_observation, upsert_kismet_observation)
from app.utils.parsing import (normalize_bettercap_row, normalize_kismet_row, parse_bettercap_upload,
    parse_csv_bytes, parse_datetime_value, parse_kismet_upload)
from app.utils.uploads import DEFAULT_IMPORT_LIMIT_BYTES, read_bounded_upload, reject_binary_text_payload

router = APIRouter()

@router.post("/api/sessions/start", status_code=201)
def start_measurement_session(request: SessionStartRequest):
    location_name = request.location_name.strip()
    if not location_name:
        raise HTTPException(status_code=400, detail="A location_name megadasa kotelezo.")

    with get_db() as conn:
        with conn.cursor() as cur:
            # Serialize session starts without a risky unique index on legacy data.
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('measurement-session-start'))")
            if SINGLE_ACTIVE_MEASUREMENT_SESSION:
                cur.execute(
                    """
                    SELECT id, location_name, started_at
                    FROM measurement_sessions
                    WHERE status = 'active'
                      AND ended_at IS NULL
                    ORDER BY started_at DESC
                    LIMIT 1
                    """
                )
                globally_active = cur.fetchone()
                if globally_active:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "active_measurement_session_exists",
                            "message": "Mar van aktiv meresi munkamenet.",
                            "active_session_id": str(globally_active["id"]),
                            "active_location_name": globally_active["location_name"],
                        },
                    )
            cur.execute(
                """
                SELECT id, location_id, location_name, started_at, ended_at,
                       operator_name, notes, environment_description, status,
                       created_at, updated_at
                FROM measurement_sessions
                WHERE lower(location_name) = lower(%s)
                  AND status = 'active'
                  AND ended_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (location_name,),
            )
            existing = cur.fetchone()
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Ezen a helyszinen mar van aktiv meresi munkamenet.",
                        "existing_session_id": str(existing["id"]),
                    },
                )

            location_id = ensure_location(cur, location_name)
            cur.execute(
                """
                INSERT INTO measurement_sessions
                  (location_id, location_name, started_at, operator_name, notes,
                   environment_description, status, created_at, updated_at)
                VALUES (%s, %s, now(), %s, %s, %s, 'active', now(), now())
                RETURNING id, location_id, location_name, started_at, ended_at,
                          operator_name, notes, environment_description, status,
                          created_at, updated_at
                """,
                (
                    location_id,
                    location_name,
                    request.operator_name.strip() if request.operator_name else None,
                    request.notes.strip() if request.notes else None,
                    request.environment_description.strip() if request.environment_description else None,
                ),
            )
            session = dict(cur.fetchone())
        conn.commit()
    return session


@router.get("/api/sessions")
def list_measurement_sessions(
    location_name: str | None = None,
    status: str | None = None,
    limit: int = 50,
):
    location_filter = location_name.strip() if location_name and location_name.strip() else None
    status_filter = status.strip().lower() if status and status.strip() else None
    if status_filter and status_filter not in {"active", "stopped", "archived"}:
        raise HTTPException(status_code=400, detail="Ervenytelen session status.")
    safe_limit = max(1, min(limit, 200))

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, location_id, location_name, started_at, ended_at,
                       operator_name, notes, environment_description, status,
                       created_at, updated_at
                FROM measurement_sessions
                WHERE (%s::text IS NULL OR lower(location_name) = lower(%s::text))
                  AND (%s::text IS NULL OR status = %s::text)
                ORDER BY started_at DESC
                LIMIT %s
                """,
                (location_filter, location_filter, status_filter, status_filter, safe_limit),
            )
            items = list(cur.fetchall())
    return {"items": items, "limit": safe_limit}


@router.get("/api/sessions/active")
def list_active_measurement_sessions(location_name: str | None = None):
    location_filter = location_name.strip() if location_name and location_name.strip() else None
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, location_id, location_name, started_at, ended_at,
                       operator_name, notes, environment_description, status,
                       created_at, updated_at
                FROM measurement_sessions
                WHERE status = 'active'
                  AND ended_at IS NULL
                  AND (%s::text IS NULL OR lower(location_name) = lower(%s::text))
                ORDER BY started_at DESC
                """,
                (location_filter, location_filter),
            )
            items = list(cur.fetchall())
    return {"items": items}


@router.get("/api/sessions/{session_id}")
def get_measurement_session(session_id: uuid.UUID):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, location_id, location_name, started_at, ended_at,
                       operator_name, notes, environment_description, status,
                       created_at, updated_at
                FROM measurement_sessions
                WHERE id = %s
                """,
                (session_id,),
            )
            session = cur.fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="A meresi munkamenet nem talalhato.")
    return dict(session)


@router.post("/api/sessions/{session_id}/stop")
def stop_measurement_session(session_id: uuid.UUID):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE measurement_sessions
                SET ended_at = COALESCE(ended_at, now()),
                    status = 'stopped',
                    updated_at = now()
                WHERE id = %s
                RETURNING id, location_id, location_name, started_at, ended_at,
                          operator_name, notes, environment_description, status,
                          created_at, updated_at
                """,
                (session_id,),
            )
            session = cur.fetchone()
        conn.commit()
    if not session:
        raise HTTPException(status_code=404, detail="A meresi munkamenet nem talalhato.")
    return dict(session)


@router.post("/api/sessions/{session_id}/sources", status_code=201)
def add_measurement_source(session_id: uuid.UUID, request: MeasurementSourceRequest):
    source_type = request.source_type.strip().lower()
    source_name = request.source_name.strip()
    source_status = request.status.strip().lower()
    if not source_type or not source_name or not source_status:
        raise HTTPException(status_code=400, detail="A source_type, source_name es status kotelezo.")
    source_config = request.config or {}

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM measurement_sessions WHERE id = %s", (session_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="A meresi munkamenet nem talalhato.")
            cur.execute(
                """
                INSERT INTO measurement_sources
                  (name, source_type, measurement_session_id, source_name,
                   device_name, adapter_name, status, config, metadata,
                   created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
                RETURNING id, measurement_session_id, source_type, source_name,
                          device_name, adapter_name, status, config,
                          created_at, updated_at
                """,
                (
                    source_name,
                    source_type,
                    session_id,
                    source_name,
                    request.device_name.strip() if request.device_name else None,
                    request.adapter_name.strip() if request.adapter_name else None,
                    source_status,
                    Jsonb(source_config),
                    Jsonb(source_config),
                ),
            )
            source = dict(cur.fetchone())
        conn.commit()
    return source


@router.get("/api/sessions/{session_id}/sources")
def list_measurement_sources(session_id: uuid.UUID):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM measurement_sessions WHERE id = %s", (session_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="A meresi munkamenet nem talalhato.")
            cur.execute(
                """
                SELECT id, measurement_session_id, source_type, source_name,
                       device_name, adapter_name, status, config,
                       created_at, updated_at
                FROM measurement_sources
                WHERE measurement_session_id = %s
                ORDER BY created_at, id
                """,
                (session_id,),
            )
            items = list(cur.fetchall())
    return {"items": items}


@router.post("/api/imports/{device_type}")
def import_device_csv(
    device_type: str,
    file: UploadFile = File(...),
    location_name: str = Form(...),
    measured_at: str | None = Form(None),
):
    device_type = device_type.strip().lower()
    if device_type not in DEVICE_IMPORT_TABLES:
        raise HTTPException(status_code=400, detail=f"Nem tamogatott eszkoztipus: {device_type}")
    filename = Path(file.filename or "upload.csv").name
    file_bytes = read_bounded_upload(
        file,
        max_bytes=DEFAULT_IMPORT_LIMIT_BYTES,
        empty_detail="Ures fajl nem importalhato.",
        too_large_detail="Az import fajl legfeljebb 50 MiB lehet.",
    )
    reject_binary_text_payload(file_bytes, label="Az import fajl")

    rows = parse_csv_bytes(file_bytes)
    fallback_time = parse_datetime_value(measured_at)
    processed_rows = 0
    failed_rows = 0

    with get_db() as conn:
        with conn.cursor() as cur:
            location_id = ensure_location(cur, location_name)
            csv_import_id = create_csv_import(cur, filename, device_type)
            uploaded_file_id = save_uploaded_file(cur, csv_import_id, filename, file_bytes, file.content_type)

            for row_number, row in enumerate(rows, start=2):
                try:
                    fields = extract_common_fields(device_type, row, fallback_time)
                    insert_device_import_row(cur, device_type, csv_import_id, location_id, row_number, row, fields)
                    if device_type == "kismet":
                        upsert_kismet_observation(cur, location_id, fields)
                    elif device_type == "bettercap_ble":
                        upsert_bluetooth_observation(cur, location_id, fields)
                    processed_rows += 1
                except Exception as exc:
                    failed_rows += 1
                    cur.execute(
                        """
                        INSERT INTO import_error_rows
                          (csv_import_id, device_type, row_number, error_message, raw_row)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (csv_import_id, device_type, row_number, str(exc), Jsonb(row)),
                    )

            status = "completed" if failed_rows == 0 else "completed_with_errors"
            cur.execute(
                """
                UPDATE csv_imports
                SET status = %s,
                    total_rows = %s,
                    processed_rows = %s,
                    failed_rows = %s,
                    completed_at = now()
                WHERE id = %s
                """,
                (status, len(rows), processed_rows, failed_rows, csv_import_id),
            )
        conn.commit()

    return {
        "csv_import_id": csv_import_id,
        "uploaded_file_id": uploaded_file_id,
        "device_type": device_type,
        "location_name": location_name,
        "total_rows": len(rows),
        "processed_rows": processed_rows,
        "failed_rows": failed_rows,
    }


@router.post("/api/import/kismet")
def import_kismet_file(
    file: UploadFile = File(...),
    measurement_session_id: str | None = Form(None),
    location_name: str | None = Form(None),
    source_name: str = Form("kismet_file_import"),
    allow_without_session: bool = Form(False),
):
    filename = Path(file.filename or "kismet_import.csv").name
    file_bytes = read_bounded_upload(
        file,
        max_bytes=DEFAULT_IMPORT_LIMIT_BYTES,
        empty_detail="Ures Kismet fajl nem importalhato.",
        too_large_detail="A Kismet import fajl legfeljebb 50 MiB lehet.",
    )
    reject_binary_text_payload(file_bytes, label="A Kismet import fajl")

    rows, first_row_number, file_format = parse_kismet_upload(
        file_bytes,
        filename,
        file.content_type,
    )
    cleaned_source_name = source_name.strip() or "kismet_file_import"
    imported_rows = 0
    skipped_rows = 0
    normalized_observations = 0
    normalized_bssids: set[str] = set()
    errors: list[dict[str, Any]] = []
    imported_at = datetime.now(timezone.utc)

    with get_db() as conn:
        with conn.cursor() as cur:
            session_id, resolved_location_name, location_id = resolve_import_session(
                cur,
                measurement_session_id,
                location_name,
                allow_without_session,
            )
            source_id = ensure_kismet_measurement_source(cur, session_id, cleaned_source_name)
            csv_import_id = create_csv_import(cur, filename, "kismet")
            uploaded_file_id = save_uploaded_file(
                cur,
                csv_import_id,
                filename,
                file_bytes,
                file.content_type,
            )

            for row_number, row in enumerate(rows, start=first_row_number):
                fields = normalize_kismet_row(row, imported_at)
                cur.execute(
                    """
                    INSERT INTO kismet_import_rows
                      (csv_import_id, location_id, measurement_session_id,
                       location_name, source_name, source_type, source_file,
                       imported_at, measured_at, row_number, mac_address, bssid,
                       ssid, channel, frequency_hz, rssi_dbm, signal_dbm,
                       noise_dbm, encryption, vendor, first_seen, last_seen,
                       packet_count, raw_row, raw_payload)
                    VALUES
                      (%s, %s, %s, %s, %s, 'kismet', %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s)
                    """,
                    (
                        csv_import_id,
                        location_id,
                        session_id,
                        resolved_location_name,
                        cleaned_source_name,
                        filename,
                        imported_at,
                        fields["observed_at"],
                        row_number,
                        fields["bssid"],
                        fields["bssid"],
                        fields["ssid"],
                        fields["channel"],
                        fields["frequency_hz"],
                        fields["rssi_dbm"],
                        fields["signal_dbm"],
                        fields["noise_dbm"],
                        fields["encryption"],
                        fields["vendor"],
                        fields["first_seen"],
                        fields["last_seen"],
                        fields["packet_count"],
                        Jsonb(row),
                        Jsonb(row),
                    ),
                )

                bssid = fields["bssid"]
                if not bssid:
                    skipped_rows += 1
                    error = {"row_number": row_number, "error": "Hianyzo vagy hibas BSSID/MAC cim."}
                    errors.append(error)
                    cur.execute(
                        """
                        INSERT INTO import_error_rows
                          (csv_import_id, device_type, row_number, error_message, raw_row)
                        VALUES (%s, 'kismet', %s, %s, %s)
                        """,
                        (csv_import_id, row_number, error["error"], Jsonb(row)),
                    )
                    continue

                try:
                    with conn.transaction():
                        cur.execute(
                            """
                            INSERT INTO wifi_devices
                              (bssid, ssid, vendor, encryption, first_seen, last_seen,
                               device_type, stable_identity, identity_confidence,
                               metadata, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
                            ON CONFLICT (bssid) DO UPDATE SET
                              ssid = COALESCE(EXCLUDED.ssid, wifi_devices.ssid),
                              vendor = COALESCE(EXCLUDED.vendor, wifi_devices.vendor),
                              encryption = COALESCE(EXCLUDED.encryption, wifi_devices.encryption),
                              device_type = CASE
                                WHEN EXCLUDED.device_type IS NOT NULL AND EXCLUDED.device_type <> 'unknown'
                                THEN EXCLUDED.device_type
                                ELSE wifi_devices.device_type
                              END,
                              stable_identity = COALESCE(EXCLUDED.stable_identity, wifi_devices.stable_identity),
                              identity_confidence = COALESCE(EXCLUDED.identity_confidence, wifi_devices.identity_confidence),
                              first_seen = LEAST(
                                COALESCE(wifi_devices.first_seen, EXCLUDED.first_seen),
                                EXCLUDED.first_seen
                              ),
                              last_seen = GREATEST(
                                COALESCE(wifi_devices.last_seen, EXCLUDED.last_seen),
                                EXCLUDED.last_seen
                              ),
                              metadata = wifi_devices.metadata || EXCLUDED.metadata,
                              updated_at = now()
                            """,
                            (
                                bssid,
                                fields["ssid"],
                                fields["vendor"],
                                fields["encryption"],
                                fields["first_seen"],
                                fields["last_seen"],
                                fields["device_type"],
                                fields["stable_identity"],
                                fields["identity_confidence"],
                                Jsonb({"last_kismet_import_id": csv_import_id}),
                            ),
                        )
                        cur.execute(
                            """
                            INSERT INTO wifi_observations
                              (time, observed_at, measurement_session_id, location_id,
                               location_name, source_id, source_name, source_type,
                               bssid, ssid, channel, frequency_hz, rssi_dbm,
                               signal_dbm, noise_dbm, encryption, device_type,
                               stable_identity, identity_confidence, packet_count,
                               observation_count, capture_source, raw_payload, metadata,
                               created_at)
                            VALUES
                              (%s, %s, %s, %s, %s, %s, %s, 'kismet', %s, %s,
                               %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s, now())
                            """,
                            (
                                fields["observed_at"],
                                fields["observed_at"],
                                session_id,
                                location_id,
                                resolved_location_name,
                                source_id,
                                cleaned_source_name,
                                bssid,
                                fields["ssid"],
                                fields["channel"],
                                fields["frequency_hz"],
                                fields["rssi_dbm"],
                                fields["signal_dbm"],
                                fields["noise_dbm"],
                                fields["encryption"],
                                fields["device_type"],
                                fields["stable_identity"],
                                fields["identity_confidence"],
                                fields["packet_count"],
                                cleaned_source_name,
                                Jsonb(row),
                                Jsonb({"kismet_import_id": csv_import_id, "source_file": filename}),
                            ),
                        )
                    normalized_bssids.add(bssid)
                    normalized_observations += 1
                    imported_rows += 1
                except Exception as exc:
                    skipped_rows += 1
                    error = {"row_number": row_number, "error": str(exc)}
                    errors.append(error)
                    cur.execute(
                        """
                        INSERT INTO import_error_rows
                          (csv_import_id, device_type, row_number, error_message, raw_row)
                        VALUES (%s, 'kismet', %s, %s, %s)
                        """,
                        (csv_import_id, row_number, error["error"], Jsonb(row)),
                    )

            import_status = "completed" if skipped_rows == 0 else "completed_with_errors"
            cur.execute(
                """
                UPDATE csv_imports
                SET status = %s,
                    total_rows = %s,
                    processed_rows = %s,
                    failed_rows = %s,
                    error_summary = %s,
                    completed_at = now()
                WHERE id = %s
                """,
                (
                    import_status,
                    len(rows),
                    imported_rows,
                    skipped_rows,
                    json.dumps(errors[:20], ensure_ascii=False) if errors else None,
                    csv_import_id,
                ),
            )
        conn.commit()

    return {
        "csv_import_id": csv_import_id,
        "uploaded_file_id": uploaded_file_id,
        "file_format": file_format,
        "source_file": filename,
        "location_name": resolved_location_name,
        "measurement_session_id": str(session_id) if session_id else None,
        "total_rows": len(rows),
        "imported_rows": imported_rows,
        "skipped_rows": skipped_rows,
        "normalized_devices": len(normalized_bssids),
        "normalized_observations": normalized_observations,
        "errors": errors[:100],
    }


@router.post("/api/import/bettercap-ble")
def import_bettercap_ble_file(
    file: UploadFile = File(...),
    measurement_session_id: str | None = Form(None),
    location_name: str | None = Form(None),
    source_name: str = Form("bettercap_ble_file_import"),
    allow_without_session: bool = Form(False),
):
    filename = Path(file.filename or "bettercap_ble_import.json").name
    file_bytes = read_bounded_upload(
        file,
        max_bytes=DEFAULT_IMPORT_LIMIT_BYTES,
        empty_detail="Ures Bettercap BLE fajl nem importalhato.",
        too_large_detail="A Bettercap BLE import fajl legfeljebb 50 MiB lehet.",
    )
    reject_binary_text_payload(file_bytes, label="A Bettercap BLE import fajl")

    rows, first_row_number, file_format = parse_bettercap_upload(
        file_bytes,
        filename,
        file.content_type,
    )
    cleaned_source_name = source_name.strip() or "bettercap_ble_file_import"
    imported_rows = 0
    skipped_rows = 0
    normalized_observations = 0
    normalized_macs: set[str] = set()
    errors: list[dict[str, Any]] = []
    imported_at = datetime.now(timezone.utc)

    with get_db() as conn:
        with conn.cursor() as cur:
            session_id, resolved_location_name, location_id = resolve_import_session(
                cur,
                measurement_session_id,
                location_name,
                allow_without_session,
            )
            source_id = ensure_bettercap_measurement_source(
                cur,
                session_id,
                cleaned_source_name,
            )
            csv_import_id = create_csv_import(cur, filename, "bettercap_ble")
            uploaded_file_id = save_uploaded_file(
                cur,
                csv_import_id,
                filename,
                file_bytes,
                file.content_type,
            )

            for row_number, row in enumerate(rows, start=first_row_number):
                fields = normalize_bettercap_row(row, imported_at)
                service_uuids = fields["service_uuids"]
                cur.execute(
                    """
                    INSERT INTO bettercap_ble_import_rows
                      (csv_import_id, location_id, measurement_session_id,
                       location_name, source_name, source_file, imported_at,
                       measured_at, row_number, mac_address, device_name,
                       rssi_dbm, vendor, service_uuid, service_uuids,
                       address_type, bluetooth_type, first_seen, last_seen,
                       raw_row, raw_payload)
                    VALUES
                      (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        csv_import_id,
                        location_id,
                        session_id,
                        resolved_location_name,
                        cleaned_source_name,
                        filename,
                        imported_at,
                        fields["observed_at"],
                        row_number,
                        fields["mac"],
                        fields["device_name"],
                        fields["rssi_dbm"],
                        fields["vendor"],
                        service_uuids[0] if service_uuids else None,
                        Jsonb(service_uuids),
                        fields["address_type"],
                        fields["bluetooth_type"],
                        fields["first_seen"],
                        fields["last_seen"],
                        Jsonb(row),
                        Jsonb(row),
                    ),
                )

                mac = fields["mac"]
                if not mac:
                    skipped_rows += 1
                    error = {"row_number": row_number, "error": "Hianyzo vagy hibas Bluetooth MAC cim."}
                    errors.append(error)
                    cur.execute(
                        """
                        INSERT INTO import_error_rows
                          (csv_import_id, device_type, row_number, error_message, raw_row)
                        VALUES (%s, 'bettercap_ble', %s, %s, %s)
                        """,
                        (csv_import_id, row_number, error["error"], Jsonb(row)),
                    )
                    continue

                try:
                    with conn.transaction():
                        cur.execute(
                            """
                            INSERT INTO bluetooth_devices
                              (mac_address, device_name, vendor, address_type,
                               bluetooth_type, vendor_resolution_method, vendor_confidence,
                               bluetooth_company_id, manufacturer_data_hash,
                               stable_identity, identity_confidence,
                               first_seen, last_seen, metadata,
                               created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
                            ON CONFLICT (mac_address) DO UPDATE SET
                              device_name = COALESCE(EXCLUDED.device_name, bluetooth_devices.device_name),
                              vendor = COALESCE(EXCLUDED.vendor, bluetooth_devices.vendor),
                              address_type = COALESCE(EXCLUDED.address_type, bluetooth_devices.address_type),
                              bluetooth_type = COALESCE(EXCLUDED.bluetooth_type, bluetooth_devices.bluetooth_type),
                              vendor_resolution_method = COALESCE(EXCLUDED.vendor_resolution_method, bluetooth_devices.vendor_resolution_method),
                              vendor_confidence = COALESCE(EXCLUDED.vendor_confidence, bluetooth_devices.vendor_confidence),
                              bluetooth_company_id = COALESCE(EXCLUDED.bluetooth_company_id, bluetooth_devices.bluetooth_company_id),
                              manufacturer_data_hash = COALESCE(EXCLUDED.manufacturer_data_hash, bluetooth_devices.manufacturer_data_hash),
                              stable_identity = COALESCE(EXCLUDED.stable_identity, bluetooth_devices.stable_identity),
                              identity_confidence = COALESCE(EXCLUDED.identity_confidence, bluetooth_devices.identity_confidence),
                              first_seen = LEAST(
                                COALESCE(bluetooth_devices.first_seen, EXCLUDED.first_seen),
                                EXCLUDED.first_seen
                              ),
                              last_seen = GREATEST(
                                COALESCE(bluetooth_devices.last_seen, EXCLUDED.last_seen),
                                EXCLUDED.last_seen
                              ),
                              metadata = bluetooth_devices.metadata || EXCLUDED.metadata,
                              updated_at = now()
                            """,
                            (
                                mac,
                                fields["device_name"],
                                fields["vendor"],
                                fields["address_type"],
                                fields["bluetooth_type"],
                                fields["vendor_resolution_method"],
                                fields["vendor_confidence"],
                                fields["bluetooth_company_id"],
                                fields["manufacturer_data_hash"],
                                fields["stable_identity"],
                                fields["identity_confidence"],
                                fields["first_seen"],
                                fields["last_seen"],
                                Jsonb({"last_bettercap_import_id": csv_import_id}),
                            ),
                        )
                        cur.execute(
                            """
                            INSERT INTO bluetooth_observations
                              (time, observed_at, measurement_session_id,
                               location_id, location_name, source_id, source_name,
                               source_type, mac_address, device_name, service_uuid,
                               service_uuids, rssi_dbm, vendor, address_type,
                               bluetooth_type, vendor_resolution_method, vendor_confidence,
                               bluetooth_company_id, manufacturer_data_hash,
                               stable_identity, identity_confidence,
                               observation_count, capture_source,
                               raw_payload, metadata, created_at)
                            VALUES
                              (%s, %s, %s, %s, %s, %s, %s, 'bettercap_ble',
                               %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                               %s, %s, %s, %s, %s, %s, %s, %s, now())
                            """,
                            (
                                fields["observed_at"],
                                fields["observed_at"],
                                session_id,
                                location_id,
                                resolved_location_name,
                                source_id,
                                cleaned_source_name,
                                mac,
                                fields["device_name"],
                                service_uuids[0] if service_uuids else None,
                                Jsonb(service_uuids),
                                fields["rssi_dbm"],
                                fields["vendor"],
                                fields["address_type"],
                                fields["bluetooth_type"],
                                fields["vendor_resolution_method"],
                                fields["vendor_confidence"],
                                fields["bluetooth_company_id"],
                                fields["manufacturer_data_hash"],
                                fields["stable_identity"],
                                fields["identity_confidence"],
                                fields["observation_count"],
                                cleaned_source_name,
                                Jsonb(row),
                                Jsonb({"bettercap_import_id": csv_import_id, "source_file": filename}),
                            ),
                        )
                    normalized_macs.add(mac)
                    normalized_observations += 1
                    imported_rows += 1
                except Exception as exc:
                    skipped_rows += 1
                    error = {"row_number": row_number, "error": str(exc)}
                    errors.append(error)
                    cur.execute(
                        """
                        INSERT INTO import_error_rows
                          (csv_import_id, device_type, row_number, error_message, raw_row)
                        VALUES (%s, 'bettercap_ble', %s, %s, %s)
                        """,
                        (csv_import_id, row_number, error["error"], Jsonb(row)),
                    )

            import_status = "completed" if skipped_rows == 0 else "completed_with_errors"
            cur.execute(
                """
                UPDATE csv_imports
                SET status = %s,
                    total_rows = %s,
                    processed_rows = %s,
                    failed_rows = %s,
                    error_summary = %s,
                    completed_at = now()
                WHERE id = %s
                """,
                (
                    import_status,
                    len(rows),
                    imported_rows,
                    skipped_rows,
                    json.dumps(errors[:20], ensure_ascii=False) if errors else None,
                    csv_import_id,
                ),
            )
        conn.commit()

    return {
        "csv_import_id": csv_import_id,
        "uploaded_file_id": uploaded_file_id,
        "file_format": file_format,
        "source_file": filename,
        "location_name": resolved_location_name,
        "measurement_session_id": str(session_id) if session_id else None,
        "total_rows": len(rows),
        "imported_rows": imported_rows,
        "skipped_rows": skipped_rows,
        "normalized_devices": len(normalized_macs),
        "normalized_observations": normalized_observations,
        "errors": errors[:100],
    }
