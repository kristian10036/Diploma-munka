from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from psycopg import sql
from psycopg.types.json import Jsonb

from app.db import get_db
from app.runtime import DEVICE_IMPORT_TABLES, UPLOAD_DIR
from app.utils.parsing import (
    parse_datetime_value,
    parse_float,
    parse_frequency_hz,
    parse_int,
    parse_mac,
    row_get,
)


def get_row_measured_at(row: dict[str, Any], fallback: datetime | None) -> datetime | None:
    return (
        parse_datetime_value(
            row_get(row, "measured_at", "timestamp", "time", "date", "first_seen", "last_seen")
        )
        or fallback
    )


def ensure_location(cur, location_name: str) -> str:
    cleaned = location_name.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="A helyszin megadasa kotelezo.")
    cur.execute("SELECT id FROM locations WHERE lower(name) = lower(%s) LIMIT 1", (cleaned,))
    existing = cur.fetchone()
    if existing:
        return str(existing["id"])
    cur.execute("INSERT INTO locations (name) VALUES (%s) RETURNING id", (cleaned,))
    return str(cur.fetchone()["id"])


def resolve_import_session(
    cur,
    measurement_session_id: str | None,
    location_name: str | None,
    allow_without_session: bool,
) -> tuple[uuid.UUID | None, str, str]:
    cleaned_location = location_name.strip() if location_name and location_name.strip() else None

    if measurement_session_id:
        try:
            session_id = uuid.UUID(measurement_session_id.strip())
        except (ValueError, AttributeError) as exc:
            raise HTTPException(
                status_code=400, detail="Ervenytelen measurement_session_id."
            ) from exc
        cur.execute(
            """
            SELECT id, location_id, location_name
            FROM measurement_sessions
            WHERE id = %s
            """,
            (session_id,),
        )
        session = cur.fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="A meresi munkamenet nem talalhato.")
        session_location = session["location_name"]
        if cleaned_location and cleaned_location.lower() != session_location.lower():
            raise HTTPException(
                status_code=400,
                detail="A location_name nem egyezik a megadott meresi munkamenet helyszinevel.",
            )
        location_id = str(session["location_id"] or ensure_location(cur, session_location))
        return session_id, session_location, location_id

    if not cleaned_location:
        cur.execute(
            """
            SELECT id, location_id, location_name
            FROM measurement_sessions
            WHERE status = 'active' AND ended_at IS NULL
            ORDER BY started_at DESC
            """
        )
        active_sessions = list(cur.fetchall())
        if len(active_sessions) > 1:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ambiguous_active_sessions",
                    "message": (
                        "Tobb aktiv meresi munkamenet van; adj meg explicit "
                        "measurement_session_id-t vagy location_name-t."
                    ),
                    "active_sessions": [
                        {"id": str(row["id"]), "location_name": row["location_name"]}
                        for row in active_sessions
                    ],
                },
            )
        if len(active_sessions) == 1:
            active_session = active_sessions[0]
            location_id = str(
                active_session["location_id"]
                or ensure_location(cur, active_session["location_name"])
            )
            return active_session["id"], active_session["location_name"], location_id
        if allow_without_session:
            cleaned_location = "Kismet live background"
        else:
            raise HTTPException(
                status_code=400,
                detail="measurement_session_id vagy location_name megadasa kotelezo.",
            )

    cur.execute(
        """
        SELECT id, location_id, location_name
        FROM measurement_sessions
        WHERE lower(location_name) = lower(%s)
          AND status = 'active'
          AND ended_at IS NULL
        ORDER BY started_at DESC
        """,
        (cleaned_location,),
    )
    active_sessions = list(cur.fetchall())
    if len(active_sessions) > 1:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ambiguous_active_sessions",
                "message": (
                    "Tobb aktiv meresi munkamenet van ezen a helyszinen; adj meg explicit "
                    "measurement_session_id-t."
                ),
                "active_sessions": [
                    {"id": str(row["id"]), "location_name": row["location_name"]}
                    for row in active_sessions
                ],
            },
        )
    if len(active_sessions) == 1:
        active_session = active_sessions[0]
        location_id = str(
            active_session["location_id"] or ensure_location(cur, active_session["location_name"])
        )
        return active_session["id"], active_session["location_name"], location_id

    if not allow_without_session:
        raise HTTPException(
            status_code=409,
            detail=(
                "Nincs aktiv meresi munkamenet ezen a helyszinen. Indits sessiont, vagy "
                "engedelyezd explicit a session nelkuli importot."
            ),
        )
    return None, cleaned_location, ensure_location(cur, cleaned_location)


def ensure_kismet_measurement_source(
    cur,
    measurement_session_id: uuid.UUID | None,
    source_name: str,
) -> uuid.UUID | None:
    if measurement_session_id is None:
        return None
    cur.execute(
        """
        SELECT id
        FROM measurement_sources
        WHERE measurement_session_id = %s
          AND source_type = 'kismet'
          AND lower(source_name) = lower(%s)
        ORDER BY created_at
        LIMIT 1
        """,
        (measurement_session_id, source_name),
    )
    existing = cur.fetchone()
    if existing:
        return existing["id"]
    source_config = {"integration": "passive_file_import", "endpoint": "/api/import/kismet"}
    cur.execute(
        """
        INSERT INTO measurement_sources
          (name, source_type, measurement_session_id, source_name, status,
           config, metadata, created_at, updated_at)
        VALUES (%s, 'kismet', %s, %s, 'configured', %s, %s, now(), now())
        RETURNING id
        """,
        (
            source_name,
            measurement_session_id,
            source_name,
            Jsonb(source_config),
            Jsonb(source_config),
        ),
    )
    return cur.fetchone()["id"]


def ensure_bettercap_measurement_source(
    cur,
    measurement_session_id: uuid.UUID | None,
    source_name: str,
) -> uuid.UUID | None:
    if measurement_session_id is None:
        return None
    cur.execute(
        """
        SELECT id
        FROM measurement_sources
        WHERE measurement_session_id = %s
          AND source_type = 'bettercap_ble'
          AND lower(source_name) = lower(%s)
        ORDER BY created_at
        LIMIT 1
        """,
        (measurement_session_id, source_name),
    )
    existing = cur.fetchone()
    if existing:
        return existing["id"]
    source_config = {
        "integration": "passive_file_import",
        "endpoint": "/api/import/bettercap-ble",
    }
    cur.execute(
        """
        INSERT INTO measurement_sources
          (name, source_type, measurement_session_id, source_name, status,
           config, metadata, created_at, updated_at)
        VALUES (%s, 'bettercap_ble', %s, %s, 'configured', %s, %s, now(), now())
        RETURNING id
        """,
        (
            source_name,
            measurement_session_id,
            source_name,
            Jsonb(source_config),
            Jsonb(source_config),
        ),
    )
    return cur.fetchone()["id"]


def create_csv_import(cur, filename: str, device_type: str) -> str:
    cur.execute(
        """
        INSERT INTO csv_imports (original_filename, import_type, status)
        VALUES (%s, %s, 'processing')
        RETURNING id
        """,
        (filename, device_type),
    )
    return str(cur.fetchone()["id"])


def save_uploaded_file(
    cur, csv_import_id: str, filename: str, file_bytes: bytes, content_type: str | None
) -> str:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name or "upload.csv"
    stored_name = f"{csv_import_id}_{safe_name}"
    storage_path = UPLOAD_DIR / stored_name
    storage_path.write_bytes(file_bytes)
    sha256 = hashlib.sha256(file_bytes).hexdigest()
    cur.execute(
        """
        INSERT INTO uploaded_files
          (csv_import_id, original_filename, storage_path, content_type, size_bytes, sha256)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (csv_import_id, filename, str(storage_path), content_type, len(file_bytes), sha256),
    )
    return str(cur.fetchone()["id"])


def parse_required_frequency(row: dict[str, Any], *keys: str) -> int:
    value = parse_frequency_hz(row_get(row, *keys))
    if value is None:
        raise ValueError(f"Hianyzo vagy hibas frekvencia mezo: {', '.join(keys)}")
    return value


def parse_required_hz(row: dict[str, Any], *keys: str) -> int:
    value = parse_int(row_get(row, *keys))
    if value is None:
        raise ValueError(f"Hianyzo vagy hibas Hz mezo: {', '.join(keys)}")
    return value


def parse_optional_hz(row: dict[str, Any], *keys: str) -> int | None:
    return parse_int(row_get(row, *keys))


def parse_required_float(row: dict[str, Any], *keys: str) -> float:
    value = parse_float(row_get(row, *keys))
    if value is None:
        raise ValueError(f"Hianyzo vagy hibas numerikus mezo: {', '.join(keys)}")
    return value


def value_or_default(row_value: Any, default_value: Any) -> Any:
    return row_value if row_value not in (None, "") else default_value


def save_reference_asset(filename: str, file_bytes: bytes) -> Path:
    reference_dir = UPLOAD_DIR / "reference_images"
    reference_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name or "reference_image"
    stored_name = f"{uuid.uuid4()}_{safe_name}"
    storage_path = reference_dir / stored_name
    storage_path.write_bytes(file_bytes)
    return storage_path


def extract_common_fields(
    device_type: str, row: dict[str, Any], fallback_time: datetime | None
) -> dict[str, Any]:
    measured_at = get_row_measured_at(row, fallback_time)
    frequency_hz = parse_frequency_hz(
        row_get(
            row,
            "frequency",
            "freq",
            "frequency_hz",
            "freq_hz",
            "frequency_mhz",
            "freq_mhz",
            "channel_frequency",
        )
    )
    power_dbm = parse_float(
        row_get(row, "power", "power_dbm", "dbm", "level", "rssi", "signal", "signal_dbm")
    )
    mac_address = parse_mac(
        row_get(row, "mac", "mac_address", "bssid", "address", "device", "device_mac")
    )

    fields: dict[str, Any] = {
        "measured_at": measured_at,
        "frequency_hz": frequency_hz,
        "power_dbm": power_dbm,
        "mac_address": mac_address,
        "rssi_dbm": parse_float(row_get(row, "rssi", "signal", "signal_dbm", "power_dbm", "dbm")),
        "vendor": row_get(row, "vendor", "manufacturer", "manuf"),
    }

    if device_type == "oscor":
        fields.update(
            {
                "bandwidth_hz": parse_frequency_hz(row_get(row, "bandwidth", "bw", "bandwidth_hz")),
                "signal_label": row_get(row, "label", "signal", "name", "description"),
            }
        )
    elif device_type == "ddf":
        fields.update(
            {
                "azimuth_deg": parse_float(row_get(row, "azimuth", "azimuth_deg", "aoa")),
                "bearing_deg": parse_float(row_get(row, "bearing", "bearing_deg", "direction")),
            }
        )
    elif device_type == "pr100":
        fields.update(
            {
                "modulation": row_get(row, "modulation", "mod", "demod"),
                "bandwidth_hz": parse_frequency_hz(row_get(row, "bandwidth", "bw", "bandwidth_hz")),
            }
        )
    elif device_type == "mesa":
        fields.update(
            {
                "signal_label": row_get(row, "label", "signal", "name", "description"),
                "classification": row_get(row, "classification", "class", "type"),
            }
        )
    elif device_type == "kismet":
        fields.update(
            {
                "ssid": row_get(row, "ssid", "network", "essid", "name"),
                "channel": parse_int(row_get(row, "channel", "chan")),
                "encryption": row_get(row, "encryption", "privacy", "security", "crypt"),
            }
        )
    elif device_type == "bettercap_ble":
        fields.update(
            {
                "device_name": row_get(row, "name", "device_name", "alias"),
                "service_uuid": row_get(row, "service_uuid", "uuid", "service"),
            }
        )

    return fields


def insert_device_import_row(
    cur,
    device_type: str,
    csv_import_id: str,
    location_id: str,
    row_number: int,
    row: dict[str, Any],
    fields: dict[str, Any],
) -> None:
    table = DEVICE_IMPORT_TABLES[device_type]
    columns = ["csv_import_id", "location_id", "measured_at", "row_number", "raw_row"]
    values: list[Any] = [
        csv_import_id,
        location_id,
        fields.get("measured_at"),
        row_number,
        Jsonb(row),
    ]

    allowed_by_device = {
        "oscor": ["frequency_hz", "power_dbm", "bandwidth_hz", "signal_label"],
        "ddf": ["frequency_hz", "power_dbm", "azimuth_deg", "bearing_deg"],
        "pr100": ["frequency_hz", "power_dbm", "modulation", "bandwidth_hz"],
        "mesa": ["frequency_hz", "power_dbm", "signal_label", "classification"],
        "kismet": [
            "mac_address",
            "ssid",
            "channel",
            "frequency_hz",
            "rssi_dbm",
            "vendor",
            "encryption",
        ],
        "bettercap_ble": ["mac_address", "device_name", "rssi_dbm", "vendor", "service_uuid"],
    }
    for column in allowed_by_device[device_type]:
        columns.append(column)
        values.append(fields.get(column))

    query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(column) for column in columns),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
    )
    cur.execute(query, values)


def upsert_kismet_observation(cur, location_id: str, fields: dict[str, Any]) -> None:
    mac = fields.get("mac_address")
    if not mac:
        return
    observed_at = fields.get("measured_at") or datetime.now(timezone.utc)
    cur.execute(
        """
        INSERT INTO wifi_devices (bssid, ssid, vendor, encryption, first_seen, last_seen)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (bssid) DO UPDATE SET
          ssid = COALESCE(EXCLUDED.ssid, wifi_devices.ssid),
          vendor = COALESCE(EXCLUDED.vendor, wifi_devices.vendor),
          encryption = COALESCE(EXCLUDED.encryption, wifi_devices.encryption),
          last_seen = GREATEST(
            COALESCE(wifi_devices.last_seen, EXCLUDED.last_seen), EXCLUDED.last_seen
          )
        """,
        (
            mac,
            fields.get("ssid"),
            fields.get("vendor"),
            fields.get("encryption"),
            observed_at,
            observed_at,
        ),
    )
    cur.execute(
        """
        INSERT INTO wifi_observations
          (time, bssid, location_id, ssid, channel, frequency_hz, rssi_dbm, capture_source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'kismet_csv')
        """,
        (
            observed_at,
            mac,
            location_id,
            fields.get("ssid"),
            fields.get("channel"),
            fields.get("frequency_hz"),
            fields.get("rssi_dbm"),
        ),
    )


def upsert_bluetooth_observation(cur, location_id: str, fields: dict[str, Any]) -> None:
    mac = fields.get("mac_address")
    if not mac:
        return
    observed_at = fields.get("measured_at") or datetime.now(timezone.utc)
    cur.execute(
        """
        INSERT INTO bluetooth_devices (mac_address, device_name, vendor, first_seen, last_seen)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (mac_address) DO UPDATE SET
          device_name = COALESCE(EXCLUDED.device_name, bluetooth_devices.device_name),
          vendor = COALESCE(EXCLUDED.vendor, bluetooth_devices.vendor),
          last_seen = GREATEST(
            COALESCE(bluetooth_devices.last_seen, EXCLUDED.last_seen), EXCLUDED.last_seen
          )
        """,
        (mac, fields.get("device_name"), fields.get("vendor"), observed_at, observed_at),
    )
    cur.execute(
        """
        INSERT INTO bluetooth_observations
          (time, mac_address, location_id, device_name, service_uuid, rssi_dbm, capture_source)
        VALUES (%s, %s, %s, %s, %s, %s, 'bettercap_ble_csv')
        """,
        (
            observed_at,
            mac,
            location_id,
            fields.get("device_name"),
            fields.get("service_uuid"),
            fields.get("rssi_dbm"),
        ),
    )


def fetch_repeated_macs(min_locations: int = 2) -> list[dict[str, Any]]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH sightings AS (
                  SELECT COALESCE(source_type, 'wifi') AS source_type, bssid AS mac_address,
                         location_id
                  FROM wifi_observations
                  WHERE bssid IS NOT NULL AND location_id IS NOT NULL
                  UNION ALL
                  SELECT COALESCE(source_type, 'bluetooth') AS source_type, mac_address, location_id
                  FROM bluetooth_observations
                  WHERE mac_address IS NOT NULL AND location_id IS NOT NULL
                  UNION ALL
                  SELECT 'kismet_import' AS source_type,
                         COALESCE(bssid, mac_address) AS mac_address, location_id
                  FROM kismet_import_rows
                  WHERE COALESCE(bssid, mac_address) IS NOT NULL AND location_id IS NOT NULL
                  UNION ALL
                  SELECT 'bettercap_ble_import' AS source_type, mac_address, location_id
                  FROM bettercap_ble_import_rows
                  WHERE mac_address IS NOT NULL AND location_id IS NOT NULL
                )
                SELECT
                  s.mac_address,
                  COUNT(*) AS observation_count,
                  COUNT(DISTINCT s.location_id) AS location_count,
                  ARRAY_AGG(DISTINCT l.name ORDER BY l.name) AS locations,
                  ARRAY_AGG(DISTINCT s.source_type ORDER BY s.source_type) AS source_types
                FROM sightings s
                JOIN locations l ON l.id = s.location_id
                GROUP BY s.mac_address
                HAVING COUNT(DISTINCT s.location_id) >= %s
                ORDER BY location_count DESC, observation_count DESC, mac_address
                """,
                (min_locations,),
            )
            return list(cur.fetchall())
