from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

PROTOCOLS = ("wifi", "bluetooth")
COMPARISON_STATES = (
    "known",
    "new",
    "changed",
    "missing",
    "uncertain_match",
    "ignored",
)


def _normalize_protocol(protocol: str) -> str:
    cleaned = (protocol or "").strip().lower()
    if cleaned not in PROTOCOLS:
        raise HTTPException(status_code=422, detail="invalid_baseline_protocol")
    return cleaned


def _service_uuid_fingerprint(service_uuids: Any) -> str | None:
    if not service_uuids:
        return None
    values = sorted({str(value).strip().lower() for value in service_uuids if value})
    return ",".join(values) if values else None


def fetch_current_wifi_snapshot(
    cur, location_name: str, session_id: Any | None
) -> list[dict[str, Any]]:
    filters = ["o.bssid = d.bssid", "lower(o.location_name) = lower(%(location_name)s)"]
    params: dict[str, Any] = {"location_name": location_name}
    if session_id:
        filters.append("o.measurement_session_id = %(session_id)s")
        params["session_id"] = session_id
    where = " AND ".join(filters)
    cur.execute(
        f"""
        SELECT d.bssid AS mac_address, d.ssid, d.vendor, d.encryption, d.device_type,
               d.stable_identity, d.identity_confidence, d.first_seen, d.last_seen,
               COALESCE(stats.observation_count, 0) AS observation_count,
               stats.latest_channel, stats.latest_frequency_hz,
               stats.rssi_min_dbm, stats.rssi_max_dbm
        FROM wifi_devices d
        LEFT JOIN LATERAL (
          SELECT COUNT(*) AS observation_count,
                 MIN(COALESCE(o.signal_dbm, o.rssi_dbm)) AS rssi_min_dbm,
                 MAX(COALESCE(o.signal_dbm, o.rssi_dbm)) AS rssi_max_dbm,
                 (ARRAY_AGG(o.channel ORDER BY COALESCE(o.observed_at, o.time) DESC))[1]
                   AS latest_channel,
                 (ARRAY_AGG(o.frequency_hz ORDER BY COALESCE(o.observed_at, o.time) DESC))[1]
                   AS latest_frequency_hz
          FROM wifi_observations o WHERE {where}
        ) stats ON TRUE
        WHERE EXISTS (SELECT 1 FROM wifi_observations o WHERE {where})
        """,
        params,
    )
    return list(cur.fetchall())


def fetch_current_bluetooth_snapshot(
    cur, location_name: str, session_id: Any | None
) -> list[dict[str, Any]]:
    filters = ["o.mac_address = d.mac_address", "lower(o.location_name) = lower(%(location_name)s)"]
    params: dict[str, Any] = {"location_name": location_name}
    if session_id:
        filters.append("o.measurement_session_id = %(session_id)s")
        params["session_id"] = session_id
    where = " AND ".join(filters)
    cur.execute(
        f"""
        SELECT d.mac_address, d.device_name, d.vendor, d.address_type, d.bluetooth_type,
               d.bluetooth_company_id, d.manufacturer_data_hash,
               d.stable_identity, d.identity_confidence, d.first_seen, d.last_seen,
               COALESCE(stats.observation_count, 0) AS observation_count,
               stats.rssi_min_dbm, stats.rssi_max_dbm, stats.latest_service_uuids
        FROM bluetooth_devices d
        LEFT JOIN LATERAL (
          SELECT COUNT(*) AS observation_count,
                 MIN(o.rssi_dbm) AS rssi_min_dbm,
                 MAX(o.rssi_dbm) AS rssi_max_dbm,
                 (ARRAY_AGG(o.service_uuids ORDER BY COALESCE(o.observed_at, o.time) DESC))[1]
                   AS latest_service_uuids
          FROM bluetooth_observations o WHERE {where}
        ) stats ON TRUE
        WHERE EXISTS (SELECT 1 FROM bluetooth_observations o WHERE {where})
        """,
        params,
    )
    return list(cur.fetchall())


def save_baseline(
    cur,
    *,
    protocol: str,
    location_name: str,
    location_id: str | None,
    session_id: Any | None,
    operator: str | None,
    notes: str | None,
    reference_set_id: str | None = None,
) -> dict[str, Any]:
    protocol = _normalize_protocol(protocol)
    cleaned_location = (location_name or "").strip()
    if not cleaned_location:
        raise HTTPException(status_code=400, detail="location_name_required")

    if protocol == "wifi":
        snapshot = fetch_current_wifi_snapshot(cur, cleaned_location, session_id)
    else:
        snapshot = fetch_current_bluetooth_snapshot(cur, cleaned_location, session_id)
    if not snapshot:
        raise HTTPException(status_code=409, detail="no_current_devices_for_location")

    cur.execute(
        "SELECT COALESCE(MAX(version), 0) AS max_version FROM device_baselines "
        "WHERE lower(location_name) = lower(%s) AND protocol = %s",
        (cleaned_location, protocol),
    )
    next_version = (cur.fetchone()["max_version"] or 0) + 1

    cur.execute(
        "UPDATE device_baselines SET is_active = false, deactivated_at = now() "
        "WHERE lower(location_name) = lower(%s) AND protocol = %s AND is_active",
        (cleaned_location, protocol),
    )

    saved = 0
    for device in snapshot:
        stable_identity = device.get("stable_identity") or device.get("mac_address")
        if not stable_identity:
            continue
        if protocol == "wifi":
            cur.execute(
                """
                INSERT INTO device_baselines
                  (location_id, location_name, protocol, stable_identity, identity_confidence,
                   mac_address, vendor, device_type, ssid, encryption,
                   typical_channel, typical_frequency_hz, typical_rssi_min_dbm,
                   typical_rssi_max_dbm,
                   first_seen, last_seen, notes, version, is_active, created_by,
                   reference_set_id, source_measurement_session_id)
                VALUES (%s, %s, 'wifi', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, true, %s, %s, %s)
                """,
                (
                    location_id,
                    cleaned_location,
                    stable_identity,
                    device.get("identity_confidence") or "unknown",
                    device.get("mac_address"),
                    device.get("vendor"),
                    device.get("device_type"),
                    device.get("ssid"),
                    device.get("encryption"),
                    device.get("latest_channel"),
                    device.get("latest_frequency_hz"),
                    device.get("rssi_min_dbm"),
                    device.get("rssi_max_dbm"),
                    device.get("first_seen"),
                    device.get("last_seen"),
                    notes,
                    next_version,
                    operator,
                    reference_set_id,
                    session_id,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO device_baselines
                  (location_id, location_name, protocol, stable_identity, identity_confidence,
                   mac_address, device_name, vendor, bluetooth_company_id, service_uuid_fingerprint,
                   manufacturer_data_hash, typical_rssi_min_dbm, typical_rssi_max_dbm,
                   first_seen, last_seen, notes, version, is_active, created_by, device_type,
                   reference_set_id, source_measurement_session_id)
                VALUES (%s, %s, 'bluetooth', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, true, %s, %s, %s, %s)
                """,
                (
                    location_id,
                    cleaned_location,
                    stable_identity,
                    device.get("identity_confidence") or "unknown",
                    device.get("mac_address"),
                    device.get("device_name"),
                    device.get("vendor"),
                    device.get("bluetooth_company_id"),
                    _service_uuid_fingerprint(device.get("latest_service_uuids")),
                    device.get("manufacturer_data_hash"),
                    device.get("rssi_min_dbm"),
                    device.get("rssi_max_dbm"),
                    device.get("first_seen"),
                    device.get("last_seen"),
                    notes,
                    next_version,
                    operator,
                    device.get("bluetooth_type"),
                    reference_set_id,
                    session_id,
                ),
            )
        saved += 1
    return {
        "protocol": protocol,
        "location_name": cleaned_location,
        "version": next_version,
        "saved_entries": saved,
    }


def deactivate_baseline(cur, *, protocol: str, location_name: str) -> dict[str, Any]:
    protocol = _normalize_protocol(protocol)
    cleaned_location = (location_name or "").strip()
    if not cleaned_location:
        raise HTTPException(status_code=400, detail="location_name_required")
    cur.execute(
        "UPDATE device_baselines SET is_active = false, deactivated_at = now() "
        "WHERE lower(location_name) = lower(%s) AND protocol = %s AND is_active RETURNING id",
        (cleaned_location, protocol),
    )
    deactivated = cur.fetchall()
    return {
        "protocol": protocol,
        "location_name": cleaned_location,
        "deactivated_entries": len(deactivated),
    }


def _seconds_since(reference: datetime | None, now: datetime) -> float | None:
    if reference is None:
        return None
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return (now - reference).total_seconds()


def compute_baseline_comparison(
    cur,
    *,
    protocol: str,
    location_name: str,
    session_id: Any | None,
    grace_seconds: float,
    reference_set_id: str | None = None,
) -> dict[str, Any]:
    protocol = _normalize_protocol(protocol)
    cleaned_location = (location_name or "").strip()
    if not cleaned_location:
        raise HTTPException(status_code=400, detail="location_name_required")

    if reference_set_id:
        cur.execute(
            "SELECT * FROM device_baselines WHERE reference_set_id = %s AND protocol = %s",
            (reference_set_id, protocol),
        )
    else:
        cur.execute(
            "SELECT * FROM device_baselines WHERE lower(location_name) = lower(%s) "
            "AND protocol = %s AND is_active",
            (cleaned_location, protocol),
        )
    baseline_rows = list(cur.fetchall())
    baseline_by_identity = {row["stable_identity"]: row for row in baseline_rows}
    active_version = baseline_rows[0]["version"] if baseline_rows else None

    if protocol == "wifi":
        current = fetch_current_wifi_snapshot(cur, cleaned_location, session_id)
    else:
        current = fetch_current_bluetooth_snapshot(cur, cleaned_location, session_id)

    now = datetime.now(timezone.utc)
    matched_identities: set[str] = set()
    items: list[dict[str, Any]] = []

    for device in current:
        identity = device.get("stable_identity") or device.get("mac_address")
        baseline_entry = baseline_by_identity.get(identity)
        status: str
        if baseline_entry is not None:
            matched_identities.add(identity)
            if baseline_entry["expected_state"] == "ignored":
                status = "ignored"
            elif protocol == "wifi":
                changed = (baseline_entry.get("ssid") or "") != (device.get("ssid") or "") or (
                    baseline_entry.get("encryption") or ""
                ) != (device.get("encryption") or "")
                status = "changed" if changed else "known"
            else:
                changed = (baseline_entry.get("vendor") or "") != (device.get("vendor") or "")
                status = "changed" if changed else "known"
        else:
            soft_match = None
            for candidate in baseline_rows:
                if candidate["stable_identity"] in matched_identities:
                    continue
                if not device.get("vendor") or not candidate.get("vendor"):
                    continue
                if (
                    str(device["vendor"]).strip().lower()
                    != str(candidate["vendor"]).strip().lower()
                ):
                    continue
                if protocol == "bluetooth" and device.get("identity_confidence") not in (
                    "low",
                    "unknown",
                ):
                    continue
                soft_match = candidate
                break
            if soft_match is not None:
                status = "uncertain_match"
            else:
                status = "new"
        items.append(
            {
                **device,
                "stable_identity": identity,
                "baseline_status": status,
                "current_values": dict(device),
                "reference_values": dict(baseline_entry) if baseline_entry is not None else None,
            }
        )

    missing_items: list[dict[str, Any]] = []
    for identity, baseline_entry in baseline_by_identity.items():
        if identity in matched_identities:
            continue
        if baseline_entry["expected_state"] == "ignored":
            status = "ignored"
        else:
            age_seconds = _seconds_since(baseline_entry.get("last_seen"), now)
            if age_seconds is not None and age_seconds < grace_seconds:
                continue
            status = "missing"
        missing_items.append(
            {
                **baseline_entry,
                "baseline_status": status,
                "current_values": None,
                "reference_values": dict(baseline_entry),
            }
        )

    summary = {state: 0 for state in COMPARISON_STATES}
    for item in items + missing_items:
        summary[item["baseline_status"]] = summary.get(item["baseline_status"], 0) + 1
    summary["total_active_devices"] = len(items)

    return {
        "protocol": protocol,
        "location_name": cleaned_location,
        "active_baseline_version": active_version,
        "grace_period_seconds": grace_seconds,
        "items": items,
        "missing": missing_items,
        "summary": summary,
    }


def baseline_status_lookup(
    cur,
    *,
    protocol: str,
    location_name: str,
    session_id: Any | None,
    grace_seconds: float,
) -> dict[str, str]:
    """Lightweight wrapper for annotating device-list endpoints with baseline_status."""
    try:
        comparison = compute_baseline_comparison(
            cur,
            protocol=protocol,
            location_name=location_name,
            session_id=session_id,
            grace_seconds=grace_seconds,
        )
    except HTTPException:
        return {}
    return {item["stable_identity"]: item["baseline_status"] for item in comparison["items"]}
