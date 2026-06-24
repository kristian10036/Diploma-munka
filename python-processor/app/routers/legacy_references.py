from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from psycopg.types.json import Jsonb

from app.db import get_db
from app.services.persistence import (create_csv_import, ensure_location, parse_optional_hz,
    parse_required_float, parse_required_frequency, save_reference_asset, save_uploaded_file, value_or_default)
from app.utils.parsing import parse_csv_bytes, parse_datetime_value, parse_float, parse_frequency_hz, parse_int, row_get
from app.utils.uploads import (REFERENCE_IMAGE_LIMIT_BYTES, REFERENCE_IMPORT_LIMIT_BYTES,
    detect_reference_image, read_bounded_upload, reject_binary_text_payload)

router = APIRouter()

@router.post("/api/references/bands/import")
def import_reference_bands_csv(
    file: UploadFile = File(...),
    source_name: str | None = Form(None),
    version: str | None = Form(None),
    location_name: str | None = Form(None),
):
    filename = Path(file.filename or "reference_bands.csv").name
    file_bytes = read_bounded_upload(
        file,
        max_bytes=REFERENCE_IMPORT_LIMIT_BYTES,
        empty_detail="Ures fajl nem importalhato.",
        too_large_detail="A referenciaimport legfeljebb 64 MiB lehet.",
    )
    reject_binary_text_payload(file_bytes, label="A referenciaimport")

    rows = parse_csv_bytes(file_bytes)
    processed_rows = 0
    failed_rows = 0

    with get_db() as conn:
        with conn.cursor() as cur:
            csv_import_id = create_csv_import(cur, filename, "reference_bands")
            uploaded_file_id = save_uploaded_file(cur, csv_import_id, filename, file_bytes, file.content_type)

            for row_number, row in enumerate(rows, start=2):
                try:
                    row_source_name = value_or_default(row_get(row, "source_name", "source"), source_name)
                    row_version = value_or_default(row_get(row, "version"), version)
                    row_location_name = value_or_default(row_get(row, "location_name", "location", "helyszin"), location_name)
                    if not row_source_name:
                        raise ValueError("source_name hianyzik.")
                    if not row_location_name:
                        raise ValueError("location_name hianyzik.")

                    location_id = ensure_location(cur, str(row_location_name))
                    start_hz = parse_optional_hz(row, "start_hz", "start_frequency_hz")
                    if start_hz is None:
                        start_hz = parse_required_frequency(row, "start", "start_frequency")
                    end_hz = parse_optional_hz(row, "end_hz", "end_frequency_hz")
                    if end_hz is None:
                        end_hz = parse_required_frequency(row, "end", "end_frequency")
                    band_name = row_get(row, "band_name", "band_label", "name", "band", "service")
                    if not band_name:
                        raise ValueError("band_name hianyzik.")

                    cur.execute(
                        """
                        INSERT INTO reference_bands
                          (source_name, version, location_id, location_name, start_hz, end_hz,
                           band_name, expected_devices, normal_min_dbm, normal_max_dbm,
                           priority, notes, raw_row, external_band_id, source_file, source_pdf_page,
                           reference_profile, confidence, peak_alarm_dbm,
                           anomaly_delta_db_above_baseline, requires_site_baseline,
                           manual_site_baseline_allowed, normal_values_are_temporary)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            str(row_source_name),
                            row_version,
                            location_id,
                            str(row_location_name),
                            start_hz,
                            end_hz,
                            str(band_name),
                            row_get(row, "expected_devices", "expected_devices_or_systems", "devices", "expected", "eszkozok"),
                            parse_float(row_get(row, "normal_min_dbm", "temporary_normal_min_dbm", "min_dbm", "normal_min")),
                            parse_float(row_get(row, "normal_max_dbm", "temporary_normal_max_dbm", "max_dbm", "normal_max")),
                            parse_int(row_get(row, "priority")) or 0,
                            row_get(row, "notes", "note", "comment", "megjegyzes"),
                            Jsonb(row),
                            row_get(row, "band_id", "external_band_id", "id"),
                            row_get(row, "source_file"),
                            parse_int(row_get(row, "source_pdf_page", "pdf_page")),
                            row_get(row, "reference_profile"),
                            row_get(row, "confidence"),
                            parse_float(row_get(row, "peak_alarm_dbm", "temporary_peak_alarm_dbm")),
                            parse_float(row_get(row, "anomaly_delta_db_above_baseline", "anomaly_delta_db")),
                            str(row_get(row, "requires_site_baseline")).strip().upper() == "TRUE",
                            str(row_get(row, "manual_site_baseline_allowed")).strip().upper() != "FALSE",
                            row_get(row, "temporary_normal_min_dbm", "temporary_normal_max_dbm") is not None,
                        ),
                    )
                    processed_rows += 1
                except Exception as exc:
                    failed_rows += 1
                    cur.execute(
                        """
                        INSERT INTO import_error_rows
                          (csv_import_id, device_type, row_number, error_message, raw_row)
                        VALUES (%s, 'reference_bands', %s, %s, %s)
                        """,
                        (csv_import_id, row_number, str(exc), Jsonb(row)),
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
        "reference_type": "bands",
        "total_rows": len(rows),
        "processed_rows": processed_rows,
        "failed_rows": failed_rows,
    }


@router.post("/api/references/spectrum/import")
def import_reference_spectrum_csv(
    file: UploadFile = File(...),
    reference_id: str | None = Form(None),
    location_name: str | None = Form(None),
    device_name: str | None = Form(None),
):
    filename = Path(file.filename or "reference_spectrum.csv").name
    file_bytes = read_bounded_upload(
        file,
        max_bytes=REFERENCE_IMPORT_LIMIT_BYTES,
        empty_detail="Ures fajl nem importalhato.",
        too_large_detail="A referenciaimport legfeljebb 64 MiB lehet.",
    )
    reject_binary_text_payload(file_bytes, label="A referenciaimport")

    rows = parse_csv_bytes(file_bytes)
    processed_rows = 0
    failed_rows = 0
    fallback_reference_id = reference_id or Path(filename).stem

    with get_db() as conn:
        with conn.cursor() as cur:
            csv_import_id = create_csv_import(cur, filename, "reference_spectrum")
            uploaded_file_id = save_uploaded_file(cur, csv_import_id, filename, file_bytes, file.content_type)

            for row_number, row in enumerate(rows, start=2):
                try:
                    row_reference_id = value_or_default(row_get(row, "reference_id", "ref_id"), fallback_reference_id)
                    row_location_name = value_or_default(row_get(row, "location_name", "location", "helyszin"), location_name)
                    row_device_name = value_or_default(row_get(row, "device_name", "device", "instrument"), device_name)
                    if not row_reference_id:
                        raise ValueError("reference_id hianyzik.")
                    if not row_location_name:
                        raise ValueError("location_name hianyzik.")

                    location_id = ensure_location(cur, str(row_location_name))
                    measured_frequency_hz = parse_optional_hz(row, "measured_frequency_hz", "frequency_hz", "freq_hz")
                    if measured_frequency_hz is None:
                        measured_frequency_hz = parse_required_frequency(row, "measured_frequency", "frequency", "freq")
                    actual_rf_frequency_hz = parse_optional_hz(row, "actual_rf_frequency_hz", "rf_frequency_hz")
                    if actual_rf_frequency_hz is None:
                        actual_rf_frequency_hz = parse_frequency_hz(row_get(row, "actual_rf_frequency", "rf_frequency"))
                    power_dbm = parse_required_float(row, "power_dbm", "power", "dbm", "level", "signal")
                    point_time = parse_datetime_value(row_get(row, "timestamp", "time", "measured_at")) or datetime.now(timezone.utc)

                    cur.execute(
                        """
                        INSERT INTO reference_spectrum_points
                          (time, reference_id, location_id, location_name, device_name, source_file,
                           measured_frequency_hz, actual_rf_frequency_hz, power_dbm,
                           rbw_hz, vbw_hz, antenna, downconverter_profile, raw_row)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            point_time,
                            str(row_reference_id),
                            location_id,
                            str(row_location_name),
                            row_device_name,
                            value_or_default(row_get(row, "source_file"), filename),
                            measured_frequency_hz,
                            actual_rf_frequency_hz or measured_frequency_hz,
                            power_dbm,
                            parse_optional_hz(row, "rbw_hz") or parse_frequency_hz(row_get(row, "rbw")),
                            parse_optional_hz(row, "vbw_hz") or parse_frequency_hz(row_get(row, "vbw")),
                            row_get(row, "antenna"),
                            row_get(row, "downconverter_profile", "downconverter"),
                            Jsonb(row),
                        ),
                    )
                    processed_rows += 1
                except Exception as exc:
                    failed_rows += 1
                    cur.execute(
                        """
                        INSERT INTO import_error_rows
                          (csv_import_id, device_type, row_number, error_message, raw_row)
                        VALUES (%s, 'reference_spectrum', %s, %s, %s)
                        """,
                        (csv_import_id, row_number, str(exc), Jsonb(row)),
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
        "reference_type": "spectrum",
        "reference_id": fallback_reference_id,
        "total_rows": len(rows),
        "processed_rows": processed_rows,
        "failed_rows": failed_rows,
    }


@router.post("/api/references/images")
def upload_reference_image(
    file: UploadFile = File(...),
    start_hz: str = Form(...),
    end_hz: str = Form(...),
    min_dbm: str = Form(...),
    max_dbm: str = Form(...),
    location_name: str | None = Form(None),
    source_name: str | None = Form(None),
    version: str | None = Form(None),
    notes: str | None = Form(None),
):
    filename = Path(file.filename or "reference_image").name
    file_bytes = read_bounded_upload(
        file,
        max_bytes=REFERENCE_IMAGE_LIMIT_BYTES,
        empty_detail="Ures kep nem toltheto fel.",
        too_large_detail="A referencia kep legfeljebb 20 MiB lehet.",
    )
    detected_image = detect_reference_image(file_bytes, filename)
    content_type = detected_image.content_type

    start_hz_value = parse_frequency_hz(start_hz)
    end_hz_value = parse_frequency_hz(end_hz)
    min_dbm_value = parse_float(min_dbm)
    max_dbm_value = parse_float(max_dbm)
    if start_hz_value is None or end_hz_value is None or end_hz_value <= start_hz_value:
        raise HTTPException(status_code=400, detail="Hibas frekvenciatartomany.")
    if min_dbm_value is None or max_dbm_value is None or max_dbm_value <= min_dbm_value:
        raise HTTPException(status_code=400, detail="Hibas dBm tartomany.")

    storage_path = save_reference_asset(filename, file_bytes)
    sha256 = hashlib.sha256(file_bytes).hexdigest()

    with get_db() as conn:
        with conn.cursor() as cur:
            location_id = ensure_location(cur, location_name) if location_name else None
            cur.execute(
                """
                INSERT INTO reference_images
                  (location_id, location_name, source_name, version, original_filename,
                   storage_path, content_type, size_bytes, sha256, start_hz, end_hz,
                   min_dbm, max_dbm, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    location_id,
                    location_name,
                    source_name,
                    version,
                    filename,
                    str(storage_path),
                    content_type,
                    len(file_bytes),
                    sha256,
                    start_hz_value,
                    end_hz_value,
                    min_dbm_value,
                    max_dbm_value,
                    notes,
                ),
            )
            image_id = str(cur.fetchone()["id"])
        conn.commit()

    return {"id": image_id, "filename": filename, "start_hz": start_hz_value, "end_hz": end_hz_value}


@router.get("/api/references/bands")
def list_reference_bands(
    start_hz: int | None = None,
    end_hz: int | None = None,
    location_name: str | None = None,
):
    clauses = []
    params: list[Any] = []
    if start_hz is not None and end_hz is not None:
        clauses.append("end_hz >= %s AND start_hz <= %s")
        params.extend([start_hz, end_hz])
    if location_name:
        clauses.append("lower(location_name) = lower(%s)")
        params.append(location_name)
    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, source_name, version, location_name, start_hz, end_hz,
                       band_name, expected_devices, normal_min_dbm, normal_max_dbm,
                       priority, notes, external_band_id, source_file, source_pdf_page,
                       reference_profile, confidence, peak_alarm_dbm,
                       anomaly_delta_db_above_baseline, requires_site_baseline,
                       manual_site_baseline_allowed, normal_values_are_temporary
                FROM reference_bands
                {where_sql}
                ORDER BY priority DESC, start_hz
                LIMIT 1000
                """,
                params,
            )
            return {"items": list(cur.fetchall())}


@router.get("/api/references/spectrum")
def list_reference_spectrum_points(
    reference_id: str | None = None,
    location_name: str | None = None,
    start_hz: int | None = None,
    end_hz: int | None = None,
    limit: int = 6000,
):
    clauses = []
    params: list[Any] = []
    if reference_id:
        clauses.append("reference_id = %s")
        params.append(reference_id)
    if location_name:
        clauses.append("lower(location_name) = lower(%s)")
        params.append(location_name)
    if start_hz is not None and end_hz is not None:
        clauses.append("COALESCE(actual_rf_frequency_hz, measured_frequency_hz) BETWEEN %s AND %s")
        params.extend([start_hz, end_hz])
    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
    safe_limit = max(100, min(limit, 20000))
    params.append(safe_limit)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT time, reference_id, location_name, device_name, source_file,
                       measured_frequency_hz, actual_rf_frequency_hz, power_dbm,
                       rbw_hz, vbw_hz, antenna, downconverter_profile
                FROM reference_spectrum_points
                {where_sql}
                ORDER BY COALESCE(actual_rf_frequency_hz, measured_frequency_hz), time DESC
                LIMIT %s
                """,
                params,
            )
            return {"items": list(cur.fetchall())}


@router.get("/api/references/images")
def list_reference_images(
    start_hz: int | None = None,
    end_hz: int | None = None,
    location_name: str | None = None,
):
    clauses = []
    params: list[Any] = []
    if start_hz is not None and end_hz is not None:
        clauses.append("end_hz >= %s AND start_hz <= %s")
        params.extend([start_hz, end_hz])
    if location_name:
        clauses.append("lower(location_name) = lower(%s)")
        params.append(location_name)
    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, location_name, source_name, version, original_filename,
                       content_type, size_bytes, start_hz, end_hz, min_dbm, max_dbm,
                       is_calibrated, notes, created_at
                FROM reference_images
                {where_sql}
                ORDER BY created_at DESC
                LIMIT 200
                """,
                params,
            )
            return {"items": list(cur.fetchall())}


@router.get("/api/references/images/{image_id}/file")
def get_reference_image_file(image_id: str):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT storage_path, content_type, original_filename FROM reference_images WHERE id = %s",
                (image_id,),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Referencia kep nem talalhato.")
    storage_path = Path(row["storage_path"])
    if not storage_path.exists():
        raise HTTPException(status_code=404, detail="Referencia kep fajl nem talalhato.")
    return FileResponse(storage_path, media_type=row["content_type"], filename=row["original_filename"])
