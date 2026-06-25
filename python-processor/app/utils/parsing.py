from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

MAC_RE = re.compile(r"(?i)\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b")


def normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", key.strip().lower())


def row_get(row: dict[str, Any], *candidate_keys: str) -> Any:
    normalized = {normalize_key(str(k)): v for k, v in row.items()}
    for key in candidate_keys:
        value = normalized.get(normalize_key(key))
        if value not in (None, ""):
            return value
    return None


def parse_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    parsed = parse_float(value)
    return int(parsed) if parsed is not None else None


def parse_frequency_hz(value: Any) -> int | None:
    parsed = parse_float(value)
    if parsed is None:
        return None
    text = str(value).strip().lower()
    if "ghz" in text:
        return int(parsed * 1_000_000_000)
    if "mhz" in text:
        return int(parsed * 1_000_000)
    if "khz" in text:
        return int(parsed * 1_000)
    if parsed <= 30_000:
        return int(parsed * 1_000_000)
    return int(parsed)


def parse_datetime_value(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        number = int(text)
        if number > 10_000_000_000:
            number = number // 1000
        return datetime.fromtimestamp(number, tz=timezone.utc)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_mac(value: Any) -> str | None:
    if value in (None, ""):
        return None
    match = MAC_RE.search(str(value))
    if not match:
        return None
    return match.group(0).upper().replace("-", ":")


def parse_csv_bytes(file_bytes: bytes) -> list[dict[str, Any]]:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = file_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            text = ""
    if not text:
        raise HTTPException(status_code=400, detail="A CSV fajl nem olvashato.")

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="A CSV fejlec hianyzik.")
    return [dict(row) for row in reader]


def parse_kismet_upload(
    file_bytes: bytes,
    filename: str,
    content_type: str | None,
) -> tuple[list[dict[str, Any]], int, str]:
    suffix = Path(filename).suffix.lower()
    is_json = suffix == ".json" or (content_type or "").lower() in {
        "application/json",
        "text/json",
    }
    if not is_json:
        return parse_csv_bytes(file_bytes), 2, "csv"

    try:
        payload = json.loads(file_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"A Kismet JSON nem olvashato: {exc}") from exc

    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, dict):
        values = next(
            (
                payload[key]
                for key in ("observations", "devices", "rows", "data")
                if isinstance(payload.get(key), list)
            ),
            [payload],
        )
    else:
        raise HTTPException(
            status_code=400, detail="A Kismet JSON objektumot vagy listat kell tartalmazzon."
        )

    rows = [dict(value) for value in values if isinstance(value, dict)]
    if not rows:
        raise HTTPException(
            status_code=400, detail="A Kismet JSON nem tartalmaz importalhato objektumot."
        )
    return rows, 1, "json"


def parse_bettercap_upload(
    file_bytes: bytes,
    filename: str,
    content_type: str | None,
) -> tuple[list[dict[str, Any]], int, str]:
    suffix = Path(filename).suffix.lower()
    stripped = file_bytes.lstrip()
    is_json = (
        suffix == ".json"
        or (content_type or "").lower() in {"application/json", "text/json"}
        or stripped.startswith((b"{", b"["))
    )
    if not is_json:
        return parse_csv_bytes(file_bytes), 2, "csv"

    try:
        payload = json.loads(file_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=400, detail=f"A Bettercap BLE JSON nem olvashato: {exc}"
        ) from exc

    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, dict):
        values = next(
            (
                payload[key]
                for key in ("devices", "observations", "rows", "events", "data")
                if isinstance(payload.get(key), list)
            ),
            [payload],
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="A Bettercap BLE JSON objektumot vagy listat kell tartalmazzon.",
        )

    rows = [dict(value) for value in values if isinstance(value, dict)]
    if not rows:
        raise HTTPException(
            status_code=400,
            detail="A Bettercap BLE JSON nem tartalmaz importalhato objektumot.",
        )
    return rows, 1, "json"


def flatten_kismet_row(row: dict[str, Any]) -> dict[str, Any]:
    flattened = dict(row)

    def visit(value: Any, prefix: str = "") -> None:
        if not isinstance(value, dict):
            return
        for key, nested in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if path not in flattened:
                flattened[path] = nested
            if prefix and "." in str(key) and str(key) not in flattened:
                flattened[str(key)] = nested
            if isinstance(nested, dict):
                visit(nested, path)

    visit(row)
    return flattened


def flatten_bettercap_row(row: dict[str, Any]) -> dict[str, Any]:
    flattened = dict(row)

    def visit(value: Any, prefix: str = "") -> None:
        if not isinstance(value, dict):
            return
        for key, nested in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if path not in flattened:
                flattened[path] = nested
            if isinstance(nested, dict):
                visit(nested, path)

    visit(row)
    return flattened


def parse_bettercap_datetime(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    parsed = parse_datetime_value(value)
    if parsed is not None and parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def normalize_service_uuids(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith(("[", "{")):
            try:
                return normalize_service_uuids(json.loads(text))
            except json.JSONDecodeError:
                pass
        values: list[Any] = re.split(r"[,;\s]+", text)
    elif isinstance(value, dict):
        direct = row_get(value, "uuid", "service_uuid", "service", "id")
        values = [direct] if direct else list(value.values())
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = [value]

    normalized: list[str] = []
    for item in values:
        if isinstance(item, dict):
            nested = row_get(item, "uuid", "service_uuid", "service", "id")
            if nested not in (None, ""):
                normalized.extend(normalize_service_uuids(nested))
            continue
        text = str(item).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def parse_bluetooth_company_id(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, dict):
        for key in ("company_id", "company", "id", "uuid"):
            parsed = parse_bluetooth_company_id(value.get(key))
            if parsed is not None:
                return parsed
        return None
    if isinstance(value, (list, tuple, set)):
        for item in value:
            parsed = parse_bluetooth_company_id(item)
            if parsed is not None:
                return parsed
        return None
    text = str(value).strip().lower()
    match = re.search(r"(?:0x)?([0-9a-f]{4})\b", text)
    if match:
        try:
            return int(match.group(1), 16)
        except ValueError:
            return None
    parsed = parse_int(text)
    return parsed if parsed is not None and 0 <= parsed <= 0xFFFF else None


def manufacturer_data_hash(value: Any) -> str | None:
    if value in (None, "", [], {}):
        return None
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalized_vendor_text(value: Any) -> str | None:
    text = kismet_text(value)
    if not text:
        return None
    if text.strip().lower() in {"unknown", "ismeretlen", "n/a", "na", "none", "null"}:
        return None
    return text


def mac_is_locally_administered(mac: str | None) -> bool:
    if not mac:
        return False
    try:
        first_octet = int(mac.split(":", 1)[0], 16)
    except (ValueError, IndexError):
        return False
    return bool(first_octet & 0b00000010)


def wifi_identity_metadata(mac: str | None, device_type: str | None) -> dict[str, str | None]:
    if not mac:
        return {"stable_identity": None, "identity_confidence": "unknown"}
    normalized_type = (device_type or "unknown").lower()
    if normalized_type == "ap":
        confidence = "medium" if mac_is_locally_administered(mac) else "high"
    elif normalized_type == "client":
        confidence = "low" if mac_is_locally_administered(mac) else "medium"
    else:
        confidence = "low" if mac_is_locally_administered(mac) else "medium"
    return {"stable_identity": mac, "identity_confidence": confidence}


def bluetooth_identity_metadata(
    *,
    mac: str | None,
    device_name: str | None,
    address_type: str | None,
    bluetooth_type: str | None,
    company_id: int | None,
    service_uuids: list[str],
    manufacturer_hash: str | None,
) -> dict[str, str | None]:
    if not mac:
        return {"stable_identity": None, "identity_confidence": "unknown"}
    address_text = (address_type or "").lower()
    is_private = any(
        token in address_text for token in ("random", "private", "resolvable", "non-resolvable")
    )
    if not is_private and not mac_is_locally_administered(mac):
        return {"stable_identity": mac, "identity_confidence": "high"}

    fingerprint_parts = {
        "name": device_name or "",
        "company_id": company_id,
        "service_uuids": sorted(str(uuid) for uuid in service_uuids if uuid),
        "manufacturer_data_hash": manufacturer_hash or "",
        "address_type": address_type or "",
        "bluetooth_type": bluetooth_type or "",
    }
    has_strong_fingerprint = bool(
        company_id or manufacturer_hash or fingerprint_parts["service_uuids"]
    )
    digest = hashlib.sha256(
        json.dumps(fingerprint_parts, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()
    return {
        "stable_identity": f"blefp:{digest}",
        "identity_confidence": "low" if has_strong_fingerprint else "unknown",
    }


def bluetooth_vendor_metadata(
    *,
    vendor: str | None,
    source: str,
    address_type: str | None,
    company_id: int | None,
    manufacturer_hash: str | None,
) -> dict[str, Any]:
    if company_id is not None:
        return {
            "vendor": vendor,
            "vendor_resolution_method": "bluetooth_company_id",
            "vendor_confidence": "high",
            "bluetooth_company_id": company_id,
            "manufacturer_data_hash": manufacturer_hash,
        }
    if vendor:
        lowered_address_type = (address_type or "").lower()
        confidence = (
            "low"
            if any(token in lowered_address_type for token in ("random", "private", "resolvable"))
            else "medium"
        )
        return {
            "vendor": vendor,
            "vendor_resolution_method": source,
            "vendor_confidence": confidence,
            "bluetooth_company_id": None,
            "manufacturer_data_hash": manufacturer_hash,
        }
    return {
        "vendor": None,
        "vendor_resolution_method": "unknown",
        "vendor_confidence": "unknown",
        "bluetooth_company_id": company_id,
        "manufacturer_data_hash": manufacturer_hash,
    }


def normalize_bettercap_row(row: dict[str, Any], fallback_time: datetime) -> dict[str, Any]:
    flattened = flatten_bettercap_row(row)
    first_seen = parse_bettercap_datetime(
        row_get(flattened, "first_seen", "firstseen", "first", "ble.first_seen", "data.first_seen")
    )
    last_seen = parse_bettercap_datetime(
        row_get(
            flattened,
            "last_seen",
            "lastseen",
            "seen",
            "timestamp",
            "time",
            "observed_at",
            "ble.last_seen",
            "data.last_seen",
            "data.timestamp",
        )
    )
    observed_at = last_seen or first_seen or fallback_time
    services = normalize_service_uuids(
        row_get(
            flattened,
            "service_uuids",
            "services",
            "uuids",
            "service_uuid",
            "service",
            "uuid",
            "ble.services",
            "data.services",
            "data.uuids",
        )
    )
    bluetooth_type = row_get(
        flattened,
        "bluetooth_type",
        "device_type",
        "type",
        "technology",
        "ble.type",
    )
    address_type = kismet_text(
        row_get(
            flattened,
            "address_type",
            "addr_type",
            "addressType",
            "ble.address_type",
            "data.address_type",
        )
    )
    vendor = normalized_vendor_text(
        row_get(
            flattened,
            "vendor",
            "manufacturer",
            "manuf",
            "company",
            "ble.vendor",
            "data.vendor",
            "data.manufacturer",
        )
    )
    manufacturer_data = row_get(
        flattened,
        "manufacturer_data",
        "manufacturerdata",
        "manufacturer_specific_data",
        "ble.manufacturer_data",
        "data.manufacturer_data",
    )
    vendor_meta = bluetooth_vendor_metadata(
        vendor=vendor,
        source="bettercap",
        address_type=address_type,
        company_id=parse_bluetooth_company_id(
            row_get(
                flattened,
                "company_id",
                "company_identifier",
                "bluetooth_company_id",
                "data.company_id",
            )
            or manufacturer_data
        ),
        manufacturer_hash=manufacturer_data_hash(manufacturer_data),
    )
    mac = parse_mac(
        row_get(
            flattened,
            "mac",
            "mac_address",
            "address",
            "addr",
            "device_mac",
            "device.address",
            "ble.mac",
            "data.mac",
            "data.address",
        )
    )
    device_name = kismet_text(
        row_get(
            flattened,
            "name",
            "device_name",
            "alias",
            "local_name",
            "ble.name",
            "data.name",
            "data.local_name",
        )
    )
    normalized_bluetooth_type = kismet_text(bluetooth_type) or "ble"
    identity_meta = bluetooth_identity_metadata(
        mac=mac,
        device_name=device_name,
        address_type=address_type,
        bluetooth_type=normalized_bluetooth_type,
        company_id=vendor_meta["bluetooth_company_id"],
        service_uuids=services,
        manufacturer_hash=vendor_meta["manufacturer_data_hash"],
    )
    return {
        "mac": mac,
        "device_name": device_name,
        "rssi_dbm": parse_float(
            row_get(
                flattened,
                "rssi_dbm",
                "rssi",
                "signal",
                "signal_dbm",
                "ble.rssi",
                "data.rssi",
                "data.signal",
            )
        ),
        "vendor": vendor_meta["vendor"],
        "vendor_resolution_method": vendor_meta["vendor_resolution_method"],
        "vendor_confidence": vendor_meta["vendor_confidence"],
        "bluetooth_company_id": vendor_meta["bluetooth_company_id"],
        "manufacturer_data_hash": vendor_meta["manufacturer_data_hash"],
        "stable_identity": identity_meta["stable_identity"],
        "identity_confidence": identity_meta["identity_confidence"],
        "service_uuids": services,
        "address_type": address_type,
        "bluetooth_type": normalized_bluetooth_type,
        "first_seen": first_seen or observed_at,
        "last_seen": last_seen or observed_at,
        "observed_at": observed_at,
        "observation_count": max(
            1,
            parse_int(row_get(flattened, "observation_count", "count", "seen_count")) or 1,
        ),
    }


def kismet_text(value: Any) -> str | None:
    if value in (None, "", 0, "0"):
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    text = str(value).strip()
    return text or None


def parse_kismet_dbm(value: Any) -> float | None:
    parsed = parse_float(value)
    # Kismet projected fields use zero when a requested signal field does not
    # exist on the device. Zero is not a meaningful passive RSSI/noise sample.
    return parsed if parsed is not None and parsed < 0 else None


def parse_kismet_frequency_hz(value: Any) -> int | None:
    if value in (None, ""):
        return None
    text = str(value).strip().lower()
    parsed = parse_float(value)
    if parsed is None:
        return None
    if "ghz" in text:
        return int(parsed * 1_000_000_000)
    if "mhz" in text:
        return int(parsed * 1_000_000)
    if "khz" in text:
        return int(parsed * 1_000)
    if parsed <= 30_000:
        return int(parsed * 1_000_000)
    if parsed < 100_000_000:
        return int(parsed * 1_000)
    return int(parsed)


def normalize_wifi_device_type(row: dict[str, Any]) -> str:
    flattened = flatten_kismet_row(row)
    candidates = [
        row_get(
            flattened,
            "device_type",
            "type",
            "role",
            "kismet.device.base.type",
            "kismet.device.base.basic_type_set",
            "dot11.device.type",
            "dot11.device.role",
            "dot11.device/dot11.device.type",
            "dot11.device/dot11.device.role",
        )
    ]
    candidates.extend(
        value
        for key, value in flattened.items()
        if any(token in str(key).lower() for token in ("type", "role"))
    )
    text = " ".join(str(value).lower() for value in candidates if value not in (None, ""))
    if any(token in text for token in ("mesh", "bridge", "wds")):
        return "bridge/mesh"
    if any(token in text for token in ("ad-hoc", "adhoc", "ibss")):
        return "ad-hoc"
    if any(
        token in text for token in ("access point", "base station", "infrastructure")
    ) or re.search(r"\bap\b", text):
        return "AP"
    if any(token in text for token in ("client", "station", " sta", "probe")):
        return "client"
    if row_get(flattened, "dot11.device.last_beaconed_ssid"):
        return "AP"
    if row_get(flattened, "dot11.device.last_probed_ssid"):
        return "client"
    return "unknown"


def normalize_kismet_row(row: dict[str, Any], fallback_time: datetime) -> dict[str, Any]:
    flattened = flatten_kismet_row(row)
    first_seen = parse_datetime_value(
        row_get(
            flattened,
            "first_seen",
            "first_time",
            "kismet.device.base.first_time",
            "kismet.device.base.first_time_sec",
        )
    )
    last_seen = parse_datetime_value(
        row_get(
            flattened,
            "last_seen",
            "last_time",
            "kismet.device.base.last_time",
            "kismet.device.base.last_time_sec",
            "timestamp",
        )
    )
    for value_name, value in (("first_seen", first_seen), ("last_seen", last_seen)):
        if value is not None and value.tzinfo is None:
            if value_name == "first_seen":
                first_seen = value.replace(tzinfo=timezone.utc)
            else:
                last_seen = value.replace(tzinfo=timezone.utc)
    observed_at = last_seen or first_seen or fallback_time

    signal_dbm = parse_kismet_dbm(
        row_get(
            flattened,
            "device_last_signal",
            "kismet.device.base.signal/kismet.common.signal.last_signal",
            "kismet.common.signal.last_signal",
            "kismet.device.base.signal.kismet.common.signal.last_signal",
            "kismet.device.base.signal.last_signal",
            "kismet.device.base.signal.last_signal_dbm",
            "signal_dbm",
            "rssi_dbm",
            "rssi",
            "signal",
        )
    )
    bssid = parse_mac(
        row_get(
            flattened,
            "bssid",
            "mac",
            "mac_address",
            "kismet.device.base.macaddr",
        )
    )
    device_type = normalize_wifi_device_type(row)
    identity_meta = wifi_identity_metadata(bssid, device_type)
    return {
        "bssid": bssid,
        "ssid": kismet_text(
            row_get(
                flattened,
                "ssid",
                "essid",
                "network",
                "kismet.device.base.name",
                "dot11.device.last_beaconed_ssid",
                "dot11.device.last_probed_ssid",
            )
        ),
        "channel": parse_int(row_get(flattened, "channel", "chan", "kismet.device.base.channel")),
        "frequency_hz": parse_kismet_frequency_hz(
            row_get(
                flattened,
                "frequency_hz",
                "frequency",
                "freq",
                "kismet.device.base.frequency",
            )
        ),
        "rssi_dbm": signal_dbm,
        "signal_dbm": signal_dbm,
        "noise_dbm": parse_kismet_dbm(
            row_get(
                flattened,
                "device_last_noise",
                "kismet.device.base.signal/kismet.common.signal.last_noise",
                "kismet.common.signal.last_noise",
                "kismet.device.base.signal.kismet.common.signal.last_noise",
                "kismet.device.base.signal.last_noise",
                "noise_dbm",
                "noise",
            )
        ),
        "encryption": kismet_text(row_get(flattened, "encryption", "security", "privacy", "crypt")),
        "vendor": kismet_text(
            row_get(flattened, "vendor", "manufacturer", "manuf", "kismet.device.base.manuf")
        ),
        "device_type": device_type,
        "stable_identity": identity_meta["stable_identity"],
        "identity_confidence": identity_meta["identity_confidence"],
        "first_seen": first_seen or observed_at,
        "last_seen": last_seen or observed_at,
        "observed_at": observed_at,
        "packet_count": parse_int(
            row_get(flattened, "packet_count", "packets", "kismet.device.base.packets.total")
        ),
    }


def is_kismet_bluetooth_row(row: dict[str, Any]) -> bool:
    flattened = flatten_kismet_row(row)
    phy_name = (
        str(
            row_get(
                flattened,
                "kismet.device.base.phyname",
                "phyname",
                "phy",
            )
            or ""
        )
        .lower()
        .strip()
    )
    device_type = (
        str(
            row_get(
                flattened,
                "kismet.device.base.type",
                "type",
                "device_type",
            )
            or ""
        )
        .lower()
        .strip()
    )

    # The projected Kismet POST response includes requested Bluetooth fields as
    # zero-valued placeholders on Wi-Fi rows. An explicit Wi-Fi PHY/type must
    # therefore win before the generic key-presence fallback.
    if "802.11" in phy_name or "wi-fi" in phy_name or "wifi" in phy_name:
        return False
    if "wi-fi" in device_type or "wifi" in device_type:
        return False
    if phy_name in {"bluetooth", "btle", "ble", "br/edr"}:
        return True
    if device_type in {"bluetooth", "btle", "ble", "br/edr"}:
        return True
    if "bluetooth_rssi_last" in flattened or "bluetooth_rssi_avg" in flattened:
        return True
    return any("bluetooth.device" in str(key) for key in flattened)


def normalize_kismet_bluetooth_row(row: dict[str, Any], fallback_time: datetime) -> dict[str, Any]:
    flattened = flatten_kismet_row(row)
    first_seen = parse_datetime_value(
        row_get(
            flattened,
            "first_seen",
            "first_time",
            "kismet.device.base.first_time",
            "kismet.device.base.first_time_sec",
        )
    )
    last_seen = parse_datetime_value(
        row_get(
            flattened,
            "last_seen",
            "last_time",
            "timestamp",
            "kismet.device.base.last_time",
            "kismet.device.base.last_time_sec",
        )
    )
    for value_name, value in (("first_seen", first_seen), ("last_seen", last_seen)):
        if value is not None and value.tzinfo is None:
            if value_name == "first_seen":
                first_seen = value.replace(tzinfo=timezone.utc)
            else:
                last_seen = value.replace(tzinfo=timezone.utc)
    observed_at = last_seen or first_seen or fallback_time

    rssi_dbm = parse_kismet_dbm(
        row_get(
            flattened,
            "bluetooth_rssi_last",
            "bluetooth_rssi_avg",
            "bluetooth.device/bluetooth.device.rssi_last",
            "bluetooth.device/bluetooth.device.rssi_avg",
            "bluetooth.device.rssi_last",
            "bluetooth.device.rssi_avg",
            "bluetooth.device.bluetooth.device.rssi_last",
            "bluetooth.device.bluetooth.device.rssi_avg",
            "device_last_signal",
            "kismet.device.base.signal/kismet.common.signal.last_signal",
            "kismet.common.signal.last_signal",
            "kismet.device.base.signal.kismet.common.signal.last_signal",
            "kismet.device.base.signal.last_signal",
            "rssi_dbm",
            "rssi",
            "signal_dbm",
            "signal",
        )
    )
    address_type = kismet_text(
        row_get(
            flattened,
            "address_type",
            "addr_type",
            "bluetooth.device.address_type",
        )
    )
    vendor = normalized_vendor_text(
        row_get(
            flattened,
            "vendor",
            "manufacturer",
            "manuf",
            "kismet.device.base.manuf",
            "bluetooth.device.vendor",
        )
    )
    manufacturer_data = row_get(
        flattened,
        "manufacturer_data",
        "manufacturerdata",
        "manufacturer_specific_data",
        "bluetooth.device.manufacturer_data",
        "bluetooth.device.manufacturerdata",
    )
    vendor_meta = bluetooth_vendor_metadata(
        vendor=vendor,
        source="kismet",
        address_type=address_type,
        company_id=parse_bluetooth_company_id(
            row_get(flattened, "company_id", "company_identifier", "bluetooth_company_id")
            or manufacturer_data
        ),
        manufacturer_hash=manufacturer_data_hash(manufacturer_data),
    )
    mac = parse_mac(
        row_get(
            flattened,
            "mac",
            "mac_address",
            "address",
            "addr",
            "kismet.device.base.macaddr",
            "bluetooth.device.address",
        )
    )
    device_name = kismet_text(
        row_get(
            flattened,
            "name",
            "device_name",
            "alias",
            "local_name",
            "kismet.device.base.name",
            "bluetooth.device.name",
            "bluetooth.device.alias",
        )
    )
    service_uuids = normalize_service_uuids(
        row_get(
            flattened,
            "service_uuids",
            "services",
            "uuids",
            "service_uuid",
            "bluetooth.device.service_uuids",
            "bluetooth.device.services",
        )
    )
    bluetooth_type = (
        kismet_text(
            row_get(
                flattened,
                "bluetooth_type",
                "kismet.device.base.type",
                "bluetooth.device.type",
                "kismet.device.base.phyname",
            )
        )
        or "bluetooth"
    )
    identity_meta = bluetooth_identity_metadata(
        mac=mac,
        device_name=device_name,
        address_type=address_type,
        bluetooth_type=bluetooth_type,
        company_id=vendor_meta["bluetooth_company_id"],
        service_uuids=service_uuids,
        manufacturer_hash=vendor_meta["manufacturer_data_hash"],
    )
    return {
        "mac": mac,
        "device_name": device_name,
        "rssi_dbm": rssi_dbm,
        "vendor": vendor_meta["vendor"],
        "vendor_resolution_method": vendor_meta["vendor_resolution_method"],
        "vendor_confidence": vendor_meta["vendor_confidence"],
        "bluetooth_company_id": vendor_meta["bluetooth_company_id"],
        "manufacturer_data_hash": vendor_meta["manufacturer_data_hash"],
        "stable_identity": identity_meta["stable_identity"],
        "identity_confidence": identity_meta["identity_confidence"],
        "service_uuids": service_uuids,
        "address_type": address_type,
        "bluetooth_type": bluetooth_type,
        "first_seen": first_seen or observed_at,
        "last_seen": last_seen or observed_at,
        "observed_at": observed_at,
        "observation_count": max(
            1,
            parse_int(
                row_get(
                    flattened,
                    "observation_count",
                    "count",
                    "seen_count",
                    "kismet.device.base.packets.total",
                )
            )
            or 1,
        ),
    }


WIFI_MANAGEMENT_FRAME_TYPES: tuple[str, ...] = (
    "beacon",
    "probe_request",
    "probe_response",
    "authentication",
    "association_request",
    "association_response",
    "reassociation",
    "disassociation",
    "deauthentication",
    "action",
)

_MANAGEMENT_FRAME_TYPE_ALIASES: dict[str, str] = {
    "beacon": "beacon",
    "probe_req": "probe_request",
    "probereq": "probe_request",
    "probe_request": "probe_request",
    "probe-request": "probe_request",
    "probe_resp": "probe_response",
    "proberesp": "probe_response",
    "probe_response": "probe_response",
    "probe-response": "probe_response",
    "auth": "authentication",
    "authentication": "authentication",
    "assoc_req": "association_request",
    "assocreq": "association_request",
    "association_request": "association_request",
    "association-request": "association_request",
    "assoc_resp": "association_response",
    "assocresp": "association_response",
    "association_response": "association_response",
    "association-response": "association_response",
    "reassoc": "reassociation",
    "reassociation": "reassociation",
    "reassociation_request": "reassociation",
    "reassociation_response": "reassociation",
    "disassoc": "disassociation",
    "disassociation": "disassociation",
    "deauth": "deauthentication",
    "deauthentication": "deauthentication",
    "deauthflood": "deauthentication",
    "bcastdiscon": "disassociation",
    "disassoctraffic": "disassociation",
    "action": "action",
}


def normalize_wifi_management_frame_type(value: Any) -> str | None:
    """Map a raw Kismet frame/alert label to one of WIFI_MANAGEMENT_FRAME_TYPES.

    Returns None instead of guessing when the raw label is not recognized, so
    unrecognized Kismet labels never get fabricated into a frame type.
    """
    text = kismet_text(value)
    if not text:
        return None
    key = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return _MANAGEMENT_FRAME_TYPE_ALIASES.get(key)


def normalize_kismet_alert_row(row: dict[str, Any], fallback_time: datetime) -> dict[str, Any]:
    flattened = flatten_kismet_row(row)
    observed_at = (
        parse_datetime_value(
            row_get(
                flattened,
                "timestamp",
                "time",
                "first_time",
                "last_time",
                "kismet.alert.timestamp",
                "kismet.alert.time",
                "kismet.alert.last_time",
            )
        )
        or fallback_time
    )
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)

    raw_severity = str(
        row_get(flattened, "severity", "priority", "kismet.alert.severity") or ""
    ).lower()
    if raw_severity in {"critical", "crit", "5"}:
        severity = "critical"
    elif raw_severity in {"error", "err", "high", "4"}:
        severity = "error"
    elif raw_severity in {"warning", "warn", "medium", "3", "2"}:
        severity = "warning"
    else:
        severity = "info"

    alert_type = (
        kismet_text(
            row_get(
                flattened,
                "alert_type",
                "type",
                "class",
                "code",
                "kismet.alert.class",
                "kismet.alert.alert",
            )
        )
        or "kismet_alert"
    )
    message = (
        kismet_text(
            row_get(
                flattened,
                "message",
                "description",
                "text",
                "kismet.alert.text",
                "kismet.alert.message",
            )
        )
        or alert_type
    )
    source_mac = parse_mac(
        row_get(flattened, "source_mac", "src_mac", "transmitter_mac", "kismet.alert.source_mac")
    )
    destination_mac = parse_mac(
        row_get(flattened, "destination_mac", "dst_mac", "victim_mac", "kismet.alert.dest_mac")
    )
    bssid = parse_mac(row_get(flattened, "bssid", "kismet.alert.bssid"))
    frame_type = kismet_text(row_get(flattened, "frame_type", "management_frame_type", "subtype"))
    reason_code = parse_int(row_get(flattened, "reason_code", "reason"))
    channel = parse_int(row_get(flattened, "channel", "chan"))
    frequency_hz = parse_kismet_frequency_hz(
        row_get(flattened, "frequency_hz", "frequency", "freq")
    )
    rssi_dbm = parse_kismet_dbm(row_get(flattened, "rssi_dbm", "signal_dbm", "signal", "rssi"))
    confidence = kismet_text(row_get(flattened, "confidence", "kismet.alert.confidence")) or "low"
    event_count = parse_int(row_get(flattened, "count", "event_count", "kismet.alert.count"))
    dedup_parts = [
        "kismet_alert",
        alert_type,
        source_mac or "",
        destination_mac or "",
        bssid or "",
        frame_type or "",
        str(reason_code or ""),
    ]
    return {
        "observed_at": observed_at,
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
        "suspected_transmitter_mac": source_mac,
        "destination_mac": destination_mac,
        "bssid": bssid,
        "ssid": kismet_text(row_get(flattened, "ssid", "network", "kismet.alert.ssid")),
        "frame_type": frame_type,
        "reason_code": reason_code,
        "channel": channel,
        "frequency_hz": frequency_hz,
        "rssi_dbm": rssi_dbm,
        "confidence": confidence,
        "event_count": event_count,
        "deduplication_key": ":".join(dedup_parts),
    }
