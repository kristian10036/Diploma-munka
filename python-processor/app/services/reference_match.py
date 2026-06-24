from __future__ import annotations

from typing import Any

PROTOCOLS = ("wifi", "bluetooth")
REFERENCE_STATUSES = ("not_compared", "in_reference", "new")

WIFI_DIFF_FIELDS = ("ssid", "encryption", "device_type", "channel", "frequency", "vendor")
BLUETOOTH_DIFF_FIELDS = (
    "device_name", "vendor", "address_type", "bluetooth_type",
    "company_id", "service_uuid_fingerprint", "manufacturer_data_hash",
)

NO_CONFIDENT_MATCH_DETAIL = "Nem találtunk megfelelően biztos referencia-egyezést."

_CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3, "certain": 4}
_PROMOTABLE_CONFIDENCE = {"certain", "high", "medium"}

MatchResult = tuple[dict[str, Any], str, str] | None


def _normalize(value: Any) -> str:
    return str(value).strip().lower() if value not in (None, "") else ""


def _service_uuid_fingerprint(service_uuids: Any) -> str | None:
    if not service_uuids:
        return None
    values = sorted({str(value).strip().lower() for value in service_uuids if value})
    return ",".join(values) if values else None


def match_wifi_identity(current: dict[str, Any], baseline_rows: list[dict[str, Any]], matched_ids: set[str]) -> MatchResult:
    identity = current.get("stable_identity") or current.get("bssid")
    if not identity:
        return None
    for baseline in baseline_rows:
        if baseline["stable_identity"] in matched_ids:
            continue
        if baseline.get("stable_identity") == identity:
            return baseline, "stable_identity", "certain"
    return None


def _bluetooth_match_candidate(current: dict[str, Any], baseline: dict[str, Any]) -> tuple[str, str] | None:
    identity = current.get("stable_identity") or current.get("mac")
    if identity and baseline.get("stable_identity") == identity:
        return "stable_identity", "certain"

    address_type = _normalize(current.get("address_type"))
    if address_type in ("public", "static") and current.get("mac") and baseline.get("mac_address"):
        if str(current["mac"]).strip().upper() == str(baseline["mac_address"]).strip().upper():
            return "public_mac", "high"

    company_id = current.get("bluetooth_company_id")
    manufacturer_hash = current.get("manufacturer_data_hash")
    if (
        company_id is not None
        and manufacturer_hash
        and company_id == baseline.get("bluetooth_company_id")
        and manufacturer_hash == baseline.get("manufacturer_data_hash")
    ):
        return "company_id_manufacturer_hash", "medium"

    fingerprint = _service_uuid_fingerprint(current.get("service_uuids"))
    if fingerprint and fingerprint == baseline.get("service_uuid_fingerprint"):
        return "service_uuid_fingerprint", "medium"

    if (
        current.get("device_name")
        and current.get("vendor")
        and _normalize(current["device_name"]) == _normalize(baseline.get("device_name"))
        and _normalize(current["vendor"]) == _normalize(baseline.get("vendor"))
    ):
        return "device_name_vendor", "low"

    return None


def match_bluetooth_identity(current: dict[str, Any], baseline_rows: list[dict[str, Any]], matched_ids: set[str]) -> MatchResult:
    best: MatchResult = None
    for baseline in baseline_rows:
        if baseline["stable_identity"] in matched_ids:
            continue
        candidate = _bluetooth_match_candidate(current, baseline)
        if candidate is None:
            continue
        method, confidence = candidate
        if best is None or _CONFIDENCE_RANK[confidence] > _CONFIDENCE_RANK[best[2]]:
            best = (baseline, method, confidence)
            if confidence == "certain":
                break
    if best is not None and best[2] not in _PROMOTABLE_CONFIDENCE:
        return None
    return best


def _wifi_value(source: dict[str, Any], field: str) -> Any:
    if field == "channel":
        return source.get("channel") if "channel" in source else source.get("typical_channel")
    if field == "frequency":
        return source.get("frequency_hz") if "frequency_hz" in source else source.get("typical_frequency_hz")
    return source.get(field)


def wifi_differences(baseline: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    differences = []
    for field in WIFI_DIFF_FIELDS:
        reference_value = _wifi_value(baseline, field)
        current_value = _wifi_value(current, field)
        if _normalize(reference_value) != _normalize(current_value):
            differences.append({"field": field, "reference_value": reference_value, "current_value": current_value})
    return differences


def _bluetooth_value(source: dict[str, Any], field: str) -> Any:
    if field == "company_id":
        return source.get("bluetooth_company_id")
    if field == "service_uuid_fingerprint":
        if "service_uuid_fingerprint" in source:
            return source.get("service_uuid_fingerprint")
        return _service_uuid_fingerprint(source.get("service_uuids"))
    return source.get(field)


def bluetooth_differences(baseline: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    differences = []
    for field in BLUETOOTH_DIFF_FIELDS:
        reference_value = _bluetooth_value(baseline, field)
        current_value = _bluetooth_value(current, field)
        if _normalize(reference_value) != _normalize(current_value):
            differences.append({"field": field, "reference_value": reference_value, "current_value": current_value})
    return differences


def annotate_devices(cur, *, items: list[dict[str, Any]], reference_set_id: Any, protocol: str) -> dict[str, Any]:
    """Annotate already-fetched session device rows with not_compared/in_reference/new
    status against an explicitly loaded reference_set, instead of the legacy
    location_name-triggered baseline lookup. Mutates each item in place and
    returns the missing-reference list plus summary counts."""
    cur.execute(
        "SELECT * FROM device_baselines WHERE reference_set_id = %s AND protocol = %s",
        (reference_set_id, protocol),
    )
    baseline_rows = list(cur.fetchall())
    matcher = match_wifi_identity if protocol == "wifi" else match_bluetooth_identity
    diff_fn = wifi_differences if protocol == "wifi" else bluetooth_differences

    matched_ids: set[str] = set()
    in_reference_count = 0
    new_count = 0
    for item in items:
        current_snapshot = dict(item)
        match = matcher(item, baseline_rows, matched_ids)
        if match is not None:
            baseline, method, confidence = match
            matched_ids.add(baseline["stable_identity"])
            differences = diff_fn(baseline, item)
            item["reference_status"] = "in_reference"
            item["has_differences"] = bool(differences)
            item["differences"] = differences
            item["match_method"] = method
            item["match_confidence"] = confidence
            item["match_detail"] = None
            item["reference_values"] = dict(baseline)
            in_reference_count += 1
        else:
            item["reference_status"] = "new"
            item["has_differences"] = False
            item["differences"] = []
            item["match_method"] = None
            item["match_confidence"] = None
            item["match_detail"] = NO_CONFIDENT_MATCH_DETAIL if protocol == "bluetooth" else None
            item["reference_values"] = None
            new_count += 1
        item["current_values"] = current_snapshot

    missing_reference = [
        dict(baseline)
        for baseline in baseline_rows
        if baseline["stable_identity"] not in matched_ids and baseline.get("expected_state") != "ignored"
    ]
    reference_summary = {
        "in_reference": in_reference_count,
        "new": new_count,
        "missing_reference": len(missing_reference),
        "total_active": len(items),
    }
    return {"reference_summary": reference_summary, "reference_missing": missing_reference}


def stamp_not_compared(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Default annotation when no reference_set_id was given: every device is
    not_compared, never known/new/missing (see ALAPELV: location_name alone
    must never imply a comparison happened)."""
    for item in items:
        item["reference_status"] = "not_compared"
        item["has_differences"] = False
        item["differences"] = []
        item["match_method"] = None
        item["match_confidence"] = None
        item["match_detail"] = None
        item["reference_values"] = None
        item["current_values"] = None
    return {
        "reference_summary": {"in_reference": 0, "new": 0, "missing_reference": 0, "total_active": len(items)},
        "reference_missing": [],
    }
