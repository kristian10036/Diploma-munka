from __future__ import annotations

from typing import Any, Iterable

from .spectrum import Detection


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()


def detect_wifi_anomalies(
    current: dict[str, Any], history: Iterable[dict[str, Any]]
) -> list[Detection]:
    rows = list(history)
    bssid = _norm(current.get("bssid") or current.get("mac_address"))
    ssid = str(current.get("ssid") or "").strip()
    location = str(current.get("location_id") or current.get("location_name") or "")
    detections: list[Detection] = []
    same_location = [
        row
        for row in rows
        if str(row.get("location_id") or row.get("location_name") or "") == location
    ]
    same_bssid = [row for row in rows if _norm(row.get("bssid") or row.get("mac_address")) == bssid]
    same_ssid = [row for row in rows if _norm(row.get("ssid")) == _norm(ssid) and ssid]

    if bssid and not any(
        _norm(row.get("bssid") or row.get("mac_address")) == bssid for row in same_location
    ):
        detections.append(
            Detection(
                "wifi",
                "new_bssid",
                "low",
                0.85,
                "Új BSSID jelent meg ezen a helyszínen.",
                evidence={"bssid": bssid, "ssid": ssid, "location": location},
            )
        )
    previous_encryptions = {
        _norm(row.get("encryption")) for row in same_ssid if row.get("encryption")
    }
    encryption = _norm(current.get("encryption"))
    if previous_encryptions and encryption and encryption not in previous_encryptions:
        detections.append(
            Detection(
                "wifi",
                "ssid_encryption_changed",
                "high",
                0.96,
                "Egy ismert SSID titkosítási tulajdonsága megváltozott.",
                evidence={
                    "ssid": ssid,
                    "previous": sorted(previous_encryptions),
                    "current": encryption,
                },
            )
        )
    if not ssid:
        detections.append(
            Detection(
                "wifi",
                "hidden_ssid",
                "low",
                0.7,
                "Rejtett vagy üres SSID-jű hozzáférési pont jelent meg.",
                evidence={"bssid": bssid},
            )
        )
    ssids_for_bssid = {_norm(row.get("ssid")) for row in same_bssid if row.get("ssid")}
    if ssid and ssids_for_bssid and _norm(ssid) not in ssids_for_bssid:
        detections.append(
            Detection(
                "wifi",
                "bssid_multiple_ssids",
                "medium",
                0.82,
                "Azonos BSSID a korábbiaktól eltérő SSID-vel jelent meg.",
                evidence={
                    "bssid": bssid,
                    "previous_ssids": sorted(ssids_for_bssid),
                    "current_ssid": ssid,
                },
            )
        )
    channel = current.get("channel")
    if isinstance(channel, (int, float)) and int(channel) not in set(range(1, 15)) | set(
        range(32, 178)
    ):
        detections.append(
            Detection(
                "wifi",
                "unusual_channel",
                "low",
                0.65,
                "A megfigyelt Wi-Fi csatorna a szokásos tartományon kívül esik.",
                evidence={"channel": channel},
            )
        )
    rssis = [float(row["rssi_dbm"]) for row in same_bssid if row.get("rssi_dbm") is not None]
    if rssis and current.get("rssi_dbm") is not None:
        baseline = sum(rssis) / len(rssis)
        delta = float(current["rssi_dbm"]) - baseline
        if abs(delta) >= 20:
            detections.append(
                Detection(
                    "wifi",
                    "rssi_behavior_changed",
                    "low",
                    0.72,
                    "Az ismert Wi-Fi eszköz RSSI-szintje jelentősen eltért a korábbitól.",
                    evidence={
                        "baseline_rssi_dbm": baseline,
                        "current_rssi_dbm": current["rssi_dbm"],
                        "delta_db": delta,
                    },
                )
            )
    vendors = {_norm(row.get("vendor")) for row in same_bssid if row.get("vendor")}
    vendor = _norm(current.get("vendor"))
    if vendors and vendor and vendor not in vendors:
        detections.append(
            Detection(
                "wifi",
                "vendor_property_mismatch",
                "low",
                0.55,
                "A vendor-adat eltér a korábbiaktól; ez csak jelzés, nem biztos azonosság.",
                evidence={"previous": sorted(vendors), "current": vendor, "certainty": "weak"},
            )
        )
    locations = {
        str(row.get("location_id") or row.get("location_name") or "") for row in same_bssid
    }
    locations.discard("")
    if location and locations and location not in locations:
        detections.append(
            Detection(
                "wifi",
                "device_seen_multiple_locations",
                "medium",
                0.8,
                "Azonos BSSID több helyszínen jelent meg.",
                evidence={"previous_locations": sorted(locations), "current_location": location},
            )
        )
    return detections


def detect_bluetooth_anomalies(
    current: dict[str, Any], history: Iterable[dict[str, Any]]
) -> list[Detection]:
    rows = list(history)
    mac = _norm(current.get("mac_address") or current.get("mac"))
    location = str(current.get("location_id") or current.get("location_name") or "")
    same_location = [
        row
        for row in rows
        if str(row.get("location_id") or row.get("location_name") or "") == location
    ]
    same_device = [row for row in rows if _norm(row.get("mac_address") or row.get("mac")) == mac]
    detections: list[Detection] = []
    if mac and not any(
        _norm(row.get("mac_address") or row.get("mac")) == mac for row in same_location
    ):
        detections.append(
            Detection(
                "bluetooth",
                "new_ble_device",
                "low",
                0.78,
                "Új Bluetooth/BLE cím jelent meg ezen a helyszínen.",
                evidence={"mac": mac, "location": location},
            )
        )
    current_services = set(
        current.get("service_uuids")
        or ([current.get("service_uuid")] if current.get("service_uuid") else [])
    )
    previous_services = set()
    previous_manufacturers = set()
    for row in same_device:
        previous_services.update(
            row.get("service_uuids")
            or ([row.get("service_uuid")] if row.get("service_uuid") else [])
        )
        if row.get("manufacturer_data"):
            previous_manufacturers.add(str(row["manufacturer_data"]))
    new_services = {
        str(value) for value in current_services if value and value not in previous_services
    }
    if previous_services and new_services:
        detections.append(
            Detection(
                "bluetooth",
                "new_service_uuid",
                "medium",
                0.84,
                "Egy ismert BLE eszköz új service UUID-t hirdet.",
                evidence={"new_service_uuids": sorted(new_services)},
            )
        )
    manufacturer = current.get("manufacturer_data")
    if previous_manufacturers and manufacturer and str(manufacturer) not in previous_manufacturers:
        detections.append(
            Detection(
                "bluetooth",
                "manufacturer_data_changed",
                "medium",
                0.8,
                "Az ismert BLE eszköz manufacturer data mezője megváltozott.",
                evidence={
                    "previous_count": len(previous_manufacturers),
                    "current": str(manufacturer),
                },
            )
        )
    rssis = [float(row["rssi_dbm"]) for row in same_device if row.get("rssi_dbm") is not None]
    if rssis and current.get("rssi_dbm") is not None:
        baseline = sum(rssis) / len(rssis)
        delta = float(current["rssi_dbm"]) - baseline
        if abs(delta) >= 20:
            detections.append(
                Detection(
                    "bluetooth",
                    "ble_rssi_behavior_changed",
                    "low",
                    0.68,
                    "Az ismert Bluetooth/BLE eszköz RSSI-viselkedése megváltozott.",
                    evidence={
                        "baseline_rssi_dbm": baseline,
                        "current_rssi_dbm": current["rssi_dbm"],
                        "delta_db": delta,
                    },
                )
            )
    locations = {
        str(row.get("location_id") or row.get("location_name") or "") for row in same_device
    }
    locations.discard("")
    if location and locations and location not in locations:
        detections.append(
            Detection(
                "bluetooth",
                "ble_seen_multiple_locations",
                "medium",
                0.65,
                "Hasonló BLE-cím több helyszínen jelent meg. Randomizált MAC miatt ez "
                "nem biztos azonosság.",
                evidence={
                    "previous_locations": sorted(locations),
                    "current_location": location,
                    "certainty": "cautious",
                },
            )
        )
    observation_count = int(current.get("observation_count") or 0)
    duration_seconds = float(current.get("presence_duration_seconds") or 0)
    if observation_count >= 100 or duration_seconds >= 3600:
        detections.append(
            Detection(
                "bluetooth",
                "unusually_persistent_presence",
                "low",
                0.72,
                "A Bluetooth/BLE eszköz szokatlanul tartósan volt jelen.",
                evidence={
                    "observation_count": observation_count,
                    "presence_duration_seconds": duration_seconds,
                },
            )
        )
    return detections
