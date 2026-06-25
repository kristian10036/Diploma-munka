from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from app.db import get_db
from app.services.csv_export import csv_export_response
from app.services.reference_match import annotate_devices, stamp_not_compared
from app.utils.parsing import parse_mac

router = APIRouter()

_BLUETOOTH_OBSERVATION_FIELDS = [
    "id",
    "measurement_session_id",
    "location_name",
    "source_name",
    "source_type",
    "observed_at",
    "mac",
    "device_name",
    "rssi_dbm",
    "vendor",
    "service_uuids",
    "address_type",
    "bluetooth_type",
    "vendor_resolution_method",
    "vendor_confidence",
    "bluetooth_company_id",
    "manufacturer_data_hash",
    "stable_identity",
    "identity_confidence",
    "observation_count",
    "raw_payload",
    "created_at",
]
_WIFI_OBSERVATION_FIELDS = [
    "id",
    "measurement_session_id",
    "location_name",
    "source_name",
    "source_type",
    "observed_at",
    "bssid",
    "ssid",
    "channel",
    "frequency_hz",
    "rssi_dbm",
    "vendor",
    "signal_dbm",
    "noise_dbm",
    "encryption",
    "device_type",
    "stable_identity",
    "identity_confidence",
    "packet_count",
    "observation_count",
    "raw_payload",
    "created_at",
]


@router.get("/api/bluetooth/devices")
def list_bluetooth_devices(
    measurement_session_id: uuid.UUID | None = None,
    location_name: str | None = None,
    mac: str | None = None,
    device_name: str | None = None,
    reference_set_id: uuid.UUID | None = None,
    require_session: bool = False,
    limit: int = 100,
):
    safe_limit = max(1, min(limit, 1000))
    if require_session and not measurement_session_id:
        return {"items": [], "limit": safe_limit, **stamp_not_compared([])}

    conditions: list[str] = []
    parameters: list[Any] = []
    if mac and mac.strip():
        conditions.append("d.mac_address = %s")
        parameters.append(parse_mac(mac) or mac.strip().upper())
    if device_name and device_name.strip():
        conditions.append("d.device_name ILIKE %s")
        parameters.append(f"%{device_name.strip()}%")

    observation_filters = ["filtered.mac_address = d.mac_address"]
    stats_filters = ["o.mac_address = d.mac_address"]
    observation_parameters: list[Any] = []
    stats_parameters: list[Any] = []
    if measurement_session_id:
        observation_filters.append("filtered.measurement_session_id = %s")
        observation_parameters.append(measurement_session_id)
        stats_filters.append("o.measurement_session_id = %s")
        stats_parameters.append(measurement_session_id)
    if location_name and location_name.strip():
        observation_filters.append("lower(filtered.location_name) = lower(%s)")
        observation_parameters.append(location_name.strip())
        stats_filters.append("lower(o.location_name) = lower(%s)")
        stats_parameters.append(location_name.strip())
    if len(observation_filters) > 1:
        conditions.append(
            "EXISTS (SELECT 1 FROM bluetooth_observations filtered WHERE "
            + " AND ".join(observation_filters)
            + ")"
        )
        parameters.extend(observation_parameters)

    where_sql = " WHERE " + " AND ".join(conditions) if conditions else ""
    stats_where_sql = " AND ".join(stats_filters)
    query = (
        """
        SELECT d.id, d.mac_address AS mac,
               COALESCE(stats.latest_device_name, d.device_name) AS device_name,
               CASE
                 WHEN COALESCE(
                   stats.latest_vendor_resolution_method, d.vendor_resolution_method, 'unknown'
                 ) = 'unknown'
                 THEN NULL
                 ELSE COALESCE(stats.latest_vendor, d.vendor)
               END AS vendor,
               COALESCE(
                 stats.latest_vendor_resolution_method, d.vendor_resolution_method, 'unknown'
               ) AS vendor_resolution_method,
               COALESCE(stats.latest_vendor_confidence, d.vendor_confidence, 'unknown')
                 AS vendor_confidence,
               COALESCE(stats.latest_bluetooth_company_id, d.bluetooth_company_id)
                 AS bluetooth_company_id,
               COALESCE(stats.latest_manufacturer_data_hash, d.manufacturer_data_hash)
                 AS manufacturer_data_hash,
               COALESCE(stats.latest_address_type, d.address_type) AS address_type,
               COALESCE(stats.latest_bluetooth_type, d.bluetooth_type) AS bluetooth_type,
               COALESCE(stats.latest_stable_identity, d.stable_identity, d.mac_address)
                 AS stable_identity,
               COALESCE(stats.latest_identity_confidence, d.identity_confidence, 'unknown')
                 AS identity_confidence,
               'unknown'::text AS baseline_status,
               'unknown'::text AS risk_level,
               NULL::text AS risk_summary,
               d.first_seen, d.last_seen,
               d.created_at, d.updated_at,
               COALESCE(stats.observation_count, 0) AS observation_count,
               stats.first_observed_at AS first_seen_in_session,
               stats.latest_observed_at AS last_seen_in_session,
               stats.latest_observed_at, stats.latest_rssi_dbm,
               stats.previous_rssi_dbm,
               stats.rssi_min_dbm, stats.rssi_max_dbm, stats.rssi_avg_dbm,
               CASE
                 WHEN stats.latest_observed_at IS NULL THEN 'unknown'
                 WHEN stats.latest_observed_at >= now() - interval '60 seconds' THEN 'present'
                 ELSE 'stale'
               END AS current_presence_state,
               COALESCE(stats.latest_service_uuids, '[]'::jsonb) AS service_uuids
        FROM bluetooth_devices d
        LEFT JOIN LATERAL (
          SELECT COUNT(*) AS observation_count,
                 MIN(COALESCE(o.observed_at, o.time)) AS first_observed_at,
                 MAX(COALESCE(o.observed_at, o.time)) AS latest_observed_at,
                 (ARRAY_AGG(o.rssi_dbm
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[1] AS latest_rssi_dbm,
                 (ARRAY_AGG(o.rssi_dbm
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[2] AS previous_rssi_dbm,
                 MIN(o.rssi_dbm) AS rssi_min_dbm,
                 MAX(o.rssi_dbm) AS rssi_max_dbm,
                 AVG(o.rssi_dbm) AS rssi_avg_dbm,
                 (ARRAY_AGG(o.device_name
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[1]
                   AS latest_device_name,
                 (ARRAY_AGG(o.vendor
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[1] AS latest_vendor,
                 (ARRAY_AGG(o.vendor_resolution_method
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[1]
                   AS latest_vendor_resolution_method,
                 (ARRAY_AGG(o.vendor_confidence
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[1]
                   AS latest_vendor_confidence,
                 (ARRAY_AGG(o.bluetooth_company_id
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[1]
                   AS latest_bluetooth_company_id,
                 (ARRAY_AGG(o.manufacturer_data_hash
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[1]
                   AS latest_manufacturer_data_hash,
                 (ARRAY_AGG(o.service_uuids
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[1]
                   AS latest_service_uuids,
                 (ARRAY_AGG(o.address_type
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[1]
                   AS latest_address_type,
                 (ARRAY_AGG(o.bluetooth_type
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[1]
                   AS latest_bluetooth_type,
                 (ARRAY_AGG(o.stable_identity
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[1]
                   AS latest_stable_identity,
                 (ARRAY_AGG(o.identity_confidence
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[1]
                   AS latest_identity_confidence
          FROM bluetooth_observations o
          WHERE 
        """
        + stats_where_sql
        + """
        ) stats ON TRUE
        """
        + where_sql
        + " ORDER BY d.last_seen DESC NULLS LAST, d.mac_address LIMIT %s"
    )
    parameters = stats_parameters + parameters + [safe_limit]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, parameters)
            items = list(cur.fetchall())
            if reference_set_id:
                reference_result = annotate_devices(
                    cur, items=items, reference_set_id=reference_set_id, protocol="bluetooth"
                )
            else:
                reference_result = stamp_not_compared(items)
    return {"items": items, "limit": safe_limit, **reference_result}


@router.get("/api/bluetooth/observations")
def list_bluetooth_observations(
    measurement_session_id: uuid.UUID | None = None,
    location_name: str | None = None,
    mac: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 500,
):
    conditions: list[str] = []
    parameters: list[Any] = []
    if measurement_session_id:
        conditions.append("o.measurement_session_id = %s")
        parameters.append(measurement_session_id)
    if location_name and location_name.strip():
        conditions.append("lower(COALESCE(o.location_name, l.name)) = lower(%s)")
        parameters.append(location_name.strip())
    if mac and mac.strip():
        conditions.append("o.mac_address = %s")
        parameters.append(parse_mac(mac) or mac.strip().upper())
    if start_time:
        conditions.append("COALESCE(o.observed_at, o.time) >= %s")
        parameters.append(start_time)
    if end_time:
        conditions.append("COALESCE(o.observed_at, o.time) <= %s")
        parameters.append(end_time)
    where_sql = " WHERE " + " AND ".join(conditions) if conditions else ""
    safe_limit = max(1, min(limit, 5000))
    query = (
        """
        SELECT o.id, o.measurement_session_id,
               COALESCE(o.location_name, l.name) AS location_name,
               COALESCE(o.source_name, o.capture_source) AS source_name,
               COALESCE(o.source_type, 'bluetooth') AS source_type,
               COALESCE(o.observed_at, o.time) AS observed_at,
               o.mac_address AS mac, o.device_name, o.rssi_dbm,
               CASE WHEN COALESCE(o.vendor_resolution_method, 'unknown') = 'unknown'
                    THEN NULL ELSE o.vendor END AS vendor,
               o.service_uuids, o.address_type, o.bluetooth_type,
               o.vendor_resolution_method, o.vendor_confidence,
               o.bluetooth_company_id, o.manufacturer_data_hash,
               COALESCE(o.stable_identity, o.mac_address) AS stable_identity,
               COALESCE(o.identity_confidence, 'unknown') AS identity_confidence,
               o.observation_count, o.raw_payload, o.created_at
        FROM bluetooth_observations o
        LEFT JOIN locations l ON l.id = o.location_id
        """
        + where_sql
        + " ORDER BY COALESCE(o.observed_at, o.time) DESC LIMIT %s"
    )
    parameters.append(safe_limit)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, parameters)
            items = list(cur.fetchall())
    return {"items": items, "limit": safe_limit}


@router.get("/api/bluetooth/observations/export")
def export_bluetooth_observations(
    measurement_session_id: uuid.UUID | None = None,
    location_name: str | None = None,
    mac: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
):
    conditions: list[str] = []
    parameters: list[Any] = []
    if measurement_session_id:
        conditions.append("o.measurement_session_id = %s")
        parameters.append(measurement_session_id)
    if location_name and location_name.strip():
        conditions.append("lower(COALESCE(o.location_name, l.name)) = lower(%s)")
        parameters.append(location_name.strip())
    if mac and mac.strip():
        conditions.append("o.mac_address = %s")
        parameters.append(parse_mac(mac) or mac.strip().upper())
    if start_time:
        conditions.append("COALESCE(o.observed_at, o.time) >= %s")
        parameters.append(start_time)
    if end_time:
        conditions.append("COALESCE(o.observed_at, o.time) <= %s")
        parameters.append(end_time)
    where_sql = " WHERE " + " AND ".join(conditions) if conditions else ""
    query = (
        """
        SELECT o.id, o.measurement_session_id,
               COALESCE(o.location_name, l.name) AS location_name,
               COALESCE(o.source_name, o.capture_source) AS source_name,
               COALESCE(o.source_type, 'bluetooth') AS source_type,
               COALESCE(o.observed_at, o.time) AS observed_at,
               o.mac_address AS mac, o.device_name, o.rssi_dbm,
               CASE WHEN COALESCE(o.vendor_resolution_method, 'unknown') = 'unknown'
                    THEN NULL ELSE o.vendor END AS vendor,
               o.service_uuids, o.address_type, o.bluetooth_type,
               o.vendor_resolution_method, o.vendor_confidence,
               o.bluetooth_company_id, o.manufacturer_data_hash,
               COALESCE(o.stable_identity, o.mac_address) AS stable_identity,
               COALESCE(o.identity_confidence, 'unknown') AS identity_confidence,
               o.observation_count, o.raw_payload, o.created_at
        FROM bluetooth_observations o
        LEFT JOIN locations l ON l.id = o.location_id
        """
        + where_sql
        + " ORDER BY COALESCE(o.observed_at, o.time) DESC"
    )

    def rows():
        with get_db() as conn:
            with conn.cursor(name="bluetooth_observations_export") as cur:
                cur.itersize = 2000
                cur.execute(query, parameters)
                yield from cur

    return csv_export_response("bluetooth_observations.csv", _BLUETOOTH_OBSERVATION_FIELDS, rows())


@router.get("/api/bluetooth/rssi-history")
def get_bluetooth_rssi_history(
    mac: str,
    measurement_session_id: uuid.UUID | None = None,
    location_name: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
):
    normalized_mac = parse_mac(mac)
    if not normalized_mac:
        raise HTTPException(status_code=400, detail="Ervenytelen Bluetooth MAC cim.")
    conditions = ["o.mac_address = %s"]
    parameters: list[Any] = [normalized_mac]
    if measurement_session_id:
        conditions.append("o.measurement_session_id = %s")
        parameters.append(measurement_session_id)
    if location_name and location_name.strip():
        conditions.append("lower(COALESCE(o.location_name, l.name)) = lower(%s)")
        parameters.append(location_name.strip())
    if start_time:
        conditions.append("COALESCE(o.observed_at, o.time) >= %s")
        parameters.append(start_time)
    if end_time:
        conditions.append("COALESCE(o.observed_at, o.time) <= %s")
        parameters.append(end_time)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COALESCE(o.observed_at, o.time) AS observed_at,
                       o.rssi_dbm,
                       COALESCE(o.location_name, l.name) AS location_name,
                       COALESCE(o.source_name, o.capture_source) AS source_name,
                       o.measurement_session_id
                FROM bluetooth_observations o
                LEFT JOIN locations l ON l.id = o.location_id
                WHERE {" AND ".join(conditions)}
                ORDER BY COALESCE(o.observed_at, o.time)
                LIMIT 10000
                """,
                parameters,
            )
            items = list(cur.fetchall())
    return {"mac": normalized_mac, "items": items}


@router.get("/api/wifi/devices")
def list_wifi_devices(
    measurement_session_id: uuid.UUID | None = None,
    location_name: str | None = None,
    ssid: str | None = None,
    bssid: str | None = None,
    reference_set_id: uuid.UUID | None = None,
    require_session: bool = False,
    limit: int = 100,
):
    safe_limit = max(1, min(limit, 1000))
    if require_session and not measurement_session_id:
        return {"items": [], "limit": safe_limit, **stamp_not_compared([])}

    conditions: list[str] = []
    parameters: list[Any] = []
    if ssid and ssid.strip():
        conditions.append("d.ssid ILIKE %s")
        parameters.append(f"%{ssid.strip()}%")
    if bssid and bssid.strip():
        conditions.append("d.bssid = %s")
        parameters.append(parse_mac(bssid) or bssid.strip().upper())

    observation_filters = ["filtered.bssid = d.bssid"]
    stats_filters = ["o.bssid = d.bssid"]
    observation_parameters: list[Any] = []
    stats_parameters: list[Any] = []
    if measurement_session_id:
        observation_filters.append("filtered.measurement_session_id = %s")
        observation_parameters.append(measurement_session_id)
        stats_filters.append("o.measurement_session_id = %s")
        stats_parameters.append(measurement_session_id)
    if location_name and location_name.strip():
        observation_filters.append("lower(filtered.location_name) = lower(%s)")
        observation_parameters.append(location_name.strip())
        stats_filters.append("lower(o.location_name) = lower(%s)")
        stats_parameters.append(location_name.strip())
    if len(observation_filters) > 1:
        conditions.append(
            "EXISTS (SELECT 1 FROM wifi_observations filtered WHERE "
            + " AND ".join(observation_filters)
            + ")"
        )
        parameters.extend(observation_parameters)

    where_sql = " WHERE " + " AND ".join(conditions) if conditions else ""
    stats_where_sql = " AND ".join(stats_filters)
    query = (
        """
        SELECT d.id, d.bssid,
               COALESCE(stats.latest_ssid, d.ssid) AS ssid,
               d.vendor,
               COALESCE(stats.latest_encryption, d.encryption) AS encryption,
               COALESCE(stats.latest_device_type, d.device_type, 'unknown') AS device_type,
               COALESCE(stats.latest_stable_identity, d.stable_identity, d.bssid)
                 AS stable_identity,
               COALESCE(stats.latest_identity_confidence, d.identity_confidence, 'unknown')
                 AS identity_confidence,
               'unknown'::text AS baseline_status,
               COALESCE(d.management_frame_counts, '{}'::jsonb) AS management_frame_summary,
               'unknown'::text AS risk_level,
               NULL::text AS risk_summary,
               d.first_seen, d.last_seen, d.notes, d.created_at, d.updated_at,
               COALESCE(stats.observation_count, 0) AS observation_count,
               stats.first_observed_at AS first_seen_in_session,
               stats.latest_observed_at AS last_seen_in_session,
               stats.latest_observed_at, stats.latest_signal_dbm,
               stats.previous_signal_dbm,
               stats.rssi_min_dbm, stats.rssi_max_dbm, stats.rssi_avg_dbm,
               CASE
                 WHEN stats.latest_observed_at IS NULL THEN 'unknown'
                 WHEN stats.latest_observed_at >= now() - interval '60 seconds' THEN 'present'
                 ELSE 'stale'
               END AS current_presence_state,
               stats.latest_channel AS channel,
               stats.latest_frequency_hz AS frequency_hz
        FROM wifi_devices d
        LEFT JOIN LATERAL (
          SELECT COUNT(*) AS observation_count,
                 MIN(COALESCE(o.observed_at, o.time)) AS first_observed_at,
                 MAX(COALESCE(o.observed_at, o.time)) AS latest_observed_at,
                 (ARRAY_AGG(COALESCE(o.signal_dbm, o.rssi_dbm)
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[1]
                   AS latest_signal_dbm,
                 (ARRAY_AGG(COALESCE(o.signal_dbm, o.rssi_dbm)
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[2]
                   AS previous_signal_dbm,
                 MIN(COALESCE(o.signal_dbm, o.rssi_dbm)) AS rssi_min_dbm,
                 MAX(COALESCE(o.signal_dbm, o.rssi_dbm)) AS rssi_max_dbm,
                 AVG(COALESCE(o.signal_dbm, o.rssi_dbm)) AS rssi_avg_dbm,
                 (ARRAY_AGG(o.ssid
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[1] AS latest_ssid,
                 (ARRAY_AGG(o.channel
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[1] AS latest_channel,
                 (ARRAY_AGG(o.frequency_hz
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[1]
                   AS latest_frequency_hz,
                 (ARRAY_AGG(o.encryption
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[1] AS latest_encryption,
                 (ARRAY_AGG(o.device_type
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[1]
                   AS latest_device_type,
                 (ARRAY_AGG(o.stable_identity
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[1]
                   AS latest_stable_identity,
                 (ARRAY_AGG(o.identity_confidence
                            ORDER BY COALESCE(o.observed_at, o.time) DESC))[1]
                   AS latest_identity_confidence
          FROM wifi_observations o
          WHERE 
        """
        + stats_where_sql
        + """
        ) stats ON TRUE
        """
        + where_sql
        + " ORDER BY d.last_seen DESC NULLS LAST, d.bssid LIMIT %s"
    )
    parameters = stats_parameters + parameters + [safe_limit]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, parameters)
            items = list(cur.fetchall())
            if reference_set_id:
                reference_result = annotate_devices(
                    cur, items=items, reference_set_id=reference_set_id, protocol="wifi"
                )
            else:
                reference_result = stamp_not_compared(items)
    return {"items": items, "limit": safe_limit, **reference_result}


@router.get("/api/wifi/observations")
def list_wifi_observations(
    measurement_session_id: uuid.UUID | None = None,
    location_name: str | None = None,
    bssid: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 500,
):
    conditions: list[str] = []
    parameters: list[Any] = []
    if measurement_session_id:
        conditions.append("o.measurement_session_id = %s")
        parameters.append(measurement_session_id)
    if location_name and location_name.strip():
        conditions.append("lower(COALESCE(o.location_name, l.name)) = lower(%s)")
        parameters.append(location_name.strip())
    if bssid and bssid.strip():
        conditions.append("o.bssid = %s")
        parameters.append(parse_mac(bssid) or bssid.strip().upper())
    if start_time:
        conditions.append("COALESCE(o.observed_at, o.time) >= %s")
        parameters.append(start_time)
    if end_time:
        conditions.append("COALESCE(o.observed_at, o.time) <= %s")
        parameters.append(end_time)
    where_sql = " WHERE " + " AND ".join(conditions) if conditions else ""
    safe_limit = max(1, min(limit, 5000))
    query = (
        """
        SELECT o.id, o.measurement_session_id,
               COALESCE(o.location_name, l.name) AS location_name,
               COALESCE(o.source_name, o.capture_source) AS source_name,
               COALESCE(o.source_type, 'wifi') AS source_type,
               COALESCE(o.observed_at, o.time) AS observed_at,
               o.bssid, o.ssid, o.channel, o.frequency_hz, o.rssi_dbm,
               d.vendor, COALESCE(o.device_type, d.device_type, 'unknown') AS device_type,
               COALESCE(o.signal_dbm, o.rssi_dbm) AS signal_dbm,
               o.noise_dbm, o.encryption, o.packet_count,
               COALESCE(o.stable_identity, o.bssid) AS stable_identity,
               COALESCE(o.identity_confidence, 'unknown') AS identity_confidence,
               o.observation_count, o.raw_payload, o.created_at
        FROM wifi_observations o
        LEFT JOIN locations l ON l.id = o.location_id
        LEFT JOIN wifi_devices d ON d.bssid = o.bssid
        """
        + where_sql
        + " ORDER BY COALESCE(o.observed_at, o.time) DESC LIMIT %s"
    )
    parameters.append(safe_limit)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, parameters)
            items = list(cur.fetchall())
    return {"items": items, "limit": safe_limit}


@router.get("/api/wifi/observations/export")
def export_wifi_observations(
    measurement_session_id: uuid.UUID | None = None,
    location_name: str | None = None,
    bssid: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
):
    conditions: list[str] = []
    parameters: list[Any] = []
    if measurement_session_id:
        conditions.append("o.measurement_session_id = %s")
        parameters.append(measurement_session_id)
    if location_name and location_name.strip():
        conditions.append("lower(COALESCE(o.location_name, l.name)) = lower(%s)")
        parameters.append(location_name.strip())
    if bssid and bssid.strip():
        conditions.append("o.bssid = %s")
        parameters.append(parse_mac(bssid) or bssid.strip().upper())
    if start_time:
        conditions.append("COALESCE(o.observed_at, o.time) >= %s")
        parameters.append(start_time)
    if end_time:
        conditions.append("COALESCE(o.observed_at, o.time) <= %s")
        parameters.append(end_time)
    where_sql = " WHERE " + " AND ".join(conditions) if conditions else ""
    query = (
        """
        SELECT o.id, o.measurement_session_id,
               COALESCE(o.location_name, l.name) AS location_name,
               COALESCE(o.source_name, o.capture_source) AS source_name,
               COALESCE(o.source_type, 'wifi') AS source_type,
               COALESCE(o.observed_at, o.time) AS observed_at,
               o.bssid, o.ssid, o.channel, o.frequency_hz, o.rssi_dbm,
               d.vendor, COALESCE(o.device_type, d.device_type, 'unknown') AS device_type,
               COALESCE(o.signal_dbm, o.rssi_dbm) AS signal_dbm,
               o.noise_dbm, o.encryption, o.packet_count,
               COALESCE(o.stable_identity, o.bssid) AS stable_identity,
               COALESCE(o.identity_confidence, 'unknown') AS identity_confidence,
               o.observation_count, o.raw_payload, o.created_at
        FROM wifi_observations o
        LEFT JOIN locations l ON l.id = o.location_id
        LEFT JOIN wifi_devices d ON d.bssid = o.bssid
        """
        + where_sql
        + " ORDER BY COALESCE(o.observed_at, o.time) DESC"
    )

    def rows():
        with get_db() as conn:
            with conn.cursor(name="wifi_observations_export") as cur:
                cur.itersize = 2000
                cur.execute(query, parameters)
                yield from cur

    return csv_export_response("wifi_observations.csv", _WIFI_OBSERVATION_FIELDS, rows())
