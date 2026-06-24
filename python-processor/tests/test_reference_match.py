from app.services.reference_match import (
    NO_CONFIDENT_MATCH_DETAIL,
    annotate_devices,
    stamp_not_compared,
)


class ScriptedCursor:
    """Same fake used in test_management_frames_and_baseline.py: returns
    scripted row sets in call order, regardless of the SQL text."""

    def __init__(self, responses):
        self._responses = list(responses)

    def execute(self, query, params=None):
        self._current = self._responses.pop(0) if self._responses else []

    def fetchall(self):
        return list(self._current)


def _wifi_baseline_row(**overrides):
    base = {
        "id": "baseline-1", "stable_identity": "AA:BB:CC:DD:EE:FF", "expected_state": "expected",
        "ssid": "Office", "encryption": "WPA2", "device_type": "AP", "vendor": "Acme",
        "typical_channel": 6, "typical_frequency_hz": 2437000000,
    }
    base.update(overrides)
    return base


def _wifi_current_item(**overrides):
    base = {
        "bssid": "AA:BB:CC:DD:EE:FF", "stable_identity": "AA:BB:CC:DD:EE:FF",
        "ssid": "Office", "encryption": "WPA2", "device_type": "AP", "vendor": "Acme",
        "channel": 6, "frequency_hz": 2437000000, "observation_count": 1,
    }
    base.update(overrides)
    return base


def test_not_compared_without_reference_set():
    items = [_wifi_current_item()]
    result = stamp_not_compared(items)
    assert items[0]["reference_status"] == "not_compared"
    assert items[0]["differences"] == []
    assert result["reference_summary"]["total_active"] == 1
    assert result["reference_missing"] == []


def test_wifi_in_reference_no_differences():
    cur = ScriptedCursor([[_wifi_baseline_row()]])
    items = [_wifi_current_item()]
    result = annotate_devices(cur, items=items, reference_set_id="ref-1", protocol="wifi")
    assert items[0]["reference_status"] == "in_reference"
    assert items[0]["has_differences"] is False
    assert items[0]["differences"] == []
    assert result["reference_summary"] == {"in_reference": 1, "new": 0, "missing_reference": 0, "total_active": 1}


def test_wifi_in_reference_with_differences_on_single_observation():
    # Even a single observation that matches the reference identity stays
    # in_reference (with has_differences), never a separate transient status.
    cur = ScriptedCursor([[_wifi_baseline_row()]])
    items = [_wifi_current_item(ssid="Evil_Twin", channel=11, observation_count=1)]
    result = annotate_devices(cur, items=items, reference_set_id="ref-1", protocol="wifi")
    assert items[0]["reference_status"] == "in_reference"
    assert items[0]["has_differences"] is True
    fields_changed = {entry["field"] for entry in items[0]["differences"]}
    assert fields_changed == {"ssid", "channel"}
    assert result["reference_summary"]["in_reference"] == 1


def test_wifi_new_device_not_in_baseline_even_with_single_observation():
    cur = ScriptedCursor([[_wifi_baseline_row()]])
    items = [_wifi_current_item(bssid="11:22:33:44:55:66", stable_identity="11:22:33:44:55:66", observation_count=1)]
    result = annotate_devices(cur, items=items, reference_set_id="ref-1", protocol="wifi")
    assert items[0]["reference_status"] == "new"
    assert items[0]["match_method"] is None
    assert result["reference_summary"]["new"] == 1


def test_wifi_missing_reference_device_listed_separately_not_in_main_items():
    cur = ScriptedCursor([[_wifi_baseline_row(stable_identity="AA:BB:CC:DD:EE:FF"), _wifi_baseline_row(stable_identity="11:22:33:44:55:66")]])
    items = [_wifi_current_item()]
    result = annotate_devices(cur, items=items, reference_set_id="ref-1", protocol="wifi")
    assert len(items) == 1
    assert result["reference_missing"][0]["stable_identity"] == "11:22:33:44:55:66"
    assert result["reference_summary"]["missing_reference"] == 1


def test_wifi_missing_reference_skips_ignored_baseline_entries():
    cur = ScriptedCursor([[_wifi_baseline_row(stable_identity="11:22:33:44:55:66", expected_state="ignored")]])
    items = []
    result = annotate_devices(cur, items=items, reference_set_id="ref-1", protocol="wifi")
    assert result["reference_missing"] == []
    assert result["reference_summary"]["missing_reference"] == 0


def _bt_baseline_row(**overrides):
    base = {
        "id": "bt-baseline-1", "stable_identity": "blefp:abc123", "expected_state": "expected",
        "mac_address": "11:22:33:44:55:66", "device_name": "My Headset", "vendor": "Acme",
        "address_type": "public", "bluetooth_type": "classic",
        "bluetooth_company_id": 76, "manufacturer_data_hash": "hash-1",
        "service_uuid_fingerprint": "180a,180f",
    }
    base.update(overrides)
    return base


def _bt_current_item(**overrides):
    base = {
        "mac": "11:22:33:44:55:66", "stable_identity": "blefp:abc123",
        "device_name": "My Headset", "vendor": "Acme", "address_type": "public",
        "bluetooth_type": "classic", "bluetooth_company_id": 76,
        "manufacturer_data_hash": "hash-1", "service_uuids": ["180a", "180f"],
        "observation_count": 1,
    }
    base.update(overrides)
    return base


def test_bluetooth_certain_stable_identity_match_is_in_reference():
    cur = ScriptedCursor([[_bt_baseline_row()]])
    items = [_bt_current_item()]
    result = annotate_devices(cur, items=items, reference_set_id="ref-1", protocol="bluetooth")
    assert items[0]["reference_status"] == "in_reference"
    assert items[0]["match_method"] == "stable_identity"
    assert items[0]["match_confidence"] == "certain"


def test_bluetooth_public_mac_match_without_stable_identity_is_in_reference():
    cur = ScriptedCursor([[_bt_baseline_row(stable_identity="blefp:other")]])
    items = [_bt_current_item(stable_identity="blefp:mine")]
    result = annotate_devices(cur, items=items, reference_set_id="ref-1", protocol="bluetooth")
    assert items[0]["reference_status"] == "in_reference"
    assert items[0]["match_method"] == "public_mac"
    assert items[0]["match_confidence"] == "high"


def test_bluetooth_random_mac_with_only_name_vendor_match_stays_new():
    # Random/private MAC + only a weak (device_name/vendor) match must not be
    # promoted to in_reference - only "megfelelő" (certain/high/medium) confidence may.
    cur = ScriptedCursor([[_bt_baseline_row(stable_identity="blefp:other", mac_address="AA:AA:AA:AA:AA:AA",
                                            bluetooth_company_id=None, manufacturer_data_hash=None,
                                            service_uuid_fingerprint=None)]])
    items = [_bt_current_item(
        mac="11:22:33:44:55:66", stable_identity="blefp:mine", address_type="random",
        bluetooth_company_id=None, manufacturer_data_hash=None, service_uuids=[],
    )]
    result = annotate_devices(cur, items=items, reference_set_id="ref-1", protocol="bluetooth")
    assert items[0]["reference_status"] == "new"
    assert items[0]["match_detail"] == NO_CONFIDENT_MATCH_DETAIL
    assert result["reference_summary"]["new"] == 1


def test_bluetooth_company_id_and_manufacturer_hash_match_is_in_reference():
    cur = ScriptedCursor([[_bt_baseline_row(stable_identity="blefp:other", mac_address="AA:AA:AA:AA:AA:AA",
                                            device_name=None, vendor=None, service_uuid_fingerprint=None)]])
    items = [_bt_current_item(
        mac="11:22:33:44:55:66", stable_identity="blefp:mine", device_name=None, vendor=None, service_uuids=[],
    )]
    result = annotate_devices(cur, items=items, reference_set_id="ref-1", protocol="bluetooth")
    assert items[0]["reference_status"] == "in_reference"
    assert items[0]["match_method"] == "company_id_manufacturer_hash"
    assert items[0]["match_confidence"] == "medium"


def test_bluetooth_differences_reported_for_vendor_change():
    cur = ScriptedCursor([[_bt_baseline_row()]])
    items = [_bt_current_item(vendor="Different Vendor Inc.")]
    result = annotate_devices(cur, items=items, reference_set_id="ref-1", protocol="bluetooth")
    assert items[0]["reference_status"] == "in_reference"
    assert items[0]["has_differences"] is True
    assert {entry["field"] for entry in items[0]["differences"]} == {"vendor"}
