from datetime import datetime, timedelta, timezone

from app.routers.health_collectors import (
    _increment_wifi_management_frame_count,
    _wifi_security_change_alerts,
)
from app.services.baseline import compute_baseline_comparison
from app.utils.parsing import normalize_wifi_management_frame_type


def test_normalize_wifi_management_frame_type_recognizes_known_aliases():
    assert normalize_wifi_management_frame_type("deauth") == "deauthentication"
    assert normalize_wifi_management_frame_type("DEAUTHFLOOD") == "deauthentication"
    assert normalize_wifi_management_frame_type("Probe Request") == "probe_request"
    assert normalize_wifi_management_frame_type("bcastdiscon") == "disassociation"
    assert normalize_wifi_management_frame_type("beacon") == "beacon"


def test_normalize_wifi_management_frame_type_does_not_guess_unknown_labels():
    assert normalize_wifi_management_frame_type("SOMETHING_KISMET_NEVER_SENDS") is None
    assert normalize_wifi_management_frame_type(None) is None
    assert normalize_wifi_management_frame_type("") is None


class RecordingCursor:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))


def test_increment_management_frame_count_skips_unrecognized_frame_type():
    cur = RecordingCursor()
    _increment_wifi_management_frame_count(cur, "AA:BB:CC:DD:EE:FF", "SYSTEM", "SYSTEM", None)
    assert cur.calls == []


def test_increment_management_frame_count_skips_without_bssid():
    cur = RecordingCursor()
    _increment_wifi_management_frame_count(cur, None, "deauthentication", "DEAUTHFLOOD", 5)
    assert cur.calls == []


def test_increment_management_frame_count_falls_back_to_alert_type_for_deauth_flood():
    cur = RecordingCursor()
    _increment_wifi_management_frame_count(cur, "AA:BB:CC:DD:EE:FF", None, "DEAUTHFLOOD", 3)
    assert len(cur.calls) == 1
    _, params = cur.calls[0]
    bssid, canonical_type, increment, canonical_type2, canonical_type3, increment2 = params
    assert bssid == "AA:BB:CC:DD:EE:FF"
    assert canonical_type == canonical_type2 == canonical_type3 == "deauthentication"
    assert increment == increment2 == 3


def test_new_open_ap_alert_uses_low_confidence_for_locally_administered_mac():
    fields = {
        "encryption": "",
        "ssid": None,
        "channel": 6,
        "frequency_hz": 2437000000,
        "rssi_dbm": -55,
    }
    alerts = _wifi_security_change_alerts(None, fields, "02:AA:BB:CC:DD:EE")
    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "new_open_ap"
    assert alerts[0]["confidence"] == "low"
    assert alerts[0]["destination_mac"] is None
    assert alerts[0]["suspected_transmitter_mac"] == "02:AA:BB:CC:DD:EE"


def test_new_open_ap_alert_uses_medium_confidence_for_globally_assigned_mac():
    fields = {
        "encryption": "open",
        "ssid": "Free WiFi",
        "channel": 1,
        "frequency_hz": 2412000000,
        "rssi_dbm": -40,
    }
    alerts = _wifi_security_change_alerts(None, fields, "00:11:22:33:44:55")
    assert len(alerts) == 1
    assert alerts[0]["confidence"] == "medium"


def test_no_new_open_ap_alert_when_first_seen_device_is_encrypted():
    fields = {
        "encryption": "WPA2",
        "ssid": "Office",
        "channel": 6,
        "frequency_hz": 2437000000,
        "rssi_dbm": -55,
    }
    assert _wifi_security_change_alerts(None, fields, "AA:BB:CC:DD:EE:FF") == []


def test_ap_security_changed_alert_fires_on_encryption_transition():
    previous = {"ssid": "Office", "encryption": "WPA2"}
    fields = {
        "ssid": "Office",
        "encryption": "open",
        "channel": 6,
        "frequency_hz": 2437000000,
        "rssi_dbm": -55,
    }
    alerts = _wifi_security_change_alerts(previous, fields, "AA:BB:CC:DD:EE:FF")
    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "ap_security_changed"
    assert alerts[0]["severity"] == "warning"
    assert alerts[0]["confidence"] == "high"


def test_bssid_fingerprint_changed_alert_fires_on_ssid_change_same_bssid():
    previous = {"ssid": "Office", "encryption": "WPA2"}
    fields = {
        "ssid": "Free_WiFi_Evil_Twin",
        "encryption": "WPA2",
        "channel": 6,
        "frequency_hz": 2437000000,
        "rssi_dbm": -55,
    }
    alerts = _wifi_security_change_alerts(previous, fields, "AA:BB:CC:DD:EE:FF")
    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "bssid_fingerprint_changed"


def test_no_alerts_when_nothing_changed():
    previous = {"ssid": "Office", "encryption": "WPA2"}
    fields = {
        "ssid": "Office",
        "encryption": "WPA2",
        "channel": 6,
        "frequency_hz": 2437000000,
        "rssi_dbm": -55,
    }
    assert _wifi_security_change_alerts(previous, fields, "AA:BB:CC:DD:EE:FF") == []


class ScriptedCursor:
    """Returns scripted row sets in call order, regardless of the SQL text,
    mirroring the simple FakeCursor approach already used in
    test_kismet_history_dedupe.py for similar dedup-helper unit tests."""

    def __init__(self, responses):
        self._responses = list(responses)
        self._current = []

    def execute(self, query, params=None):
        self._current = self._responses.pop(0) if self._responses else []

    def fetchall(self):
        return list(self._current)

    def fetchone(self):
        return self._current[0] if self._current else None


def _wifi_baseline_row(**overrides):
    base = {
        "id": "baseline-1",
        "stable_identity": "AA:BB:CC:DD:EE:FF",
        "expected_state": "expected",
        "ssid": "Office",
        "encryption": "WPA2",
        "vendor": "Acme",
        "last_seen": datetime.now(timezone.utc),
        "version": 1,
    }
    base.update(overrides)
    return base


def _wifi_current_row(**overrides):
    base = {
        "mac_address": "AA:BB:CC:DD:EE:FF",
        "stable_identity": "AA:BB:CC:DD:EE:FF",
        "ssid": "Office",
        "encryption": "WPA2",
        "vendor": "Acme",
        "device_type": "AP",
        "identity_confidence": "high",
        "observation_count": 10,
    }
    base.update(overrides)
    return base


def test_baseline_comparison_known_device_unchanged():
    cur = ScriptedCursor([[_wifi_baseline_row()], [_wifi_current_row()]])
    result = compute_baseline_comparison(
        cur, protocol="wifi", location_name="Lab", session_id=None, grace_seconds=180
    )
    assert result["items"][0]["baseline_status"] == "known"
    assert result["summary"]["known"] == 1
    assert result["missing"] == []


def test_baseline_comparison_changed_device_ssid_differs():
    cur = ScriptedCursor([[_wifi_baseline_row()], [_wifi_current_row(ssid="Different_SSID")]])
    result = compute_baseline_comparison(
        cur, protocol="wifi", location_name="Lab", session_id=None, grace_seconds=180
    )
    assert result["items"][0]["baseline_status"] == "changed"


def test_baseline_comparison_new_device_not_in_baseline():
    cur = ScriptedCursor([[], [_wifi_current_row(observation_count=50)]])
    result = compute_baseline_comparison(
        cur, protocol="wifi", location_name="Lab", session_id=None, grace_seconds=180
    )
    assert result["items"][0]["baseline_status"] == "new"


def test_baseline_comparison_new_for_single_observation_unmatched_device():
    # observation_count alone must never downgrade an unmatched device to a
    # separate "transient" bucket - even a single observation is "new".
    cur = ScriptedCursor([[], [_wifi_current_row(observation_count=1)]])
    result = compute_baseline_comparison(
        cur, protocol="wifi", location_name="Lab", session_id=None, grace_seconds=180
    )
    assert result["items"][0]["baseline_status"] == "new"


def test_baseline_comparison_missing_only_after_grace_period():
    old_last_seen = datetime.now(timezone.utc) - timedelta(seconds=500)
    cur = ScriptedCursor([[_wifi_baseline_row(last_seen=old_last_seen)], []])
    result = compute_baseline_comparison(
        cur, protocol="wifi", location_name="Lab", session_id=None, grace_seconds=180
    )
    assert len(result["missing"]) == 1
    assert result["missing"][0]["baseline_status"] == "missing"


def test_baseline_comparison_skips_missing_inside_grace_period():
    recent_last_seen = datetime.now(timezone.utc) - timedelta(seconds=30)
    cur = ScriptedCursor([[_wifi_baseline_row(last_seen=recent_last_seen)], []])
    result = compute_baseline_comparison(
        cur, protocol="wifi", location_name="Lab", session_id=None, grace_seconds=180
    )
    assert result["missing"] == []
    assert result["summary"]["missing"] == 0


def test_baseline_comparison_ignored_entry_not_seen_stays_ignored_not_missing():
    old_last_seen = datetime.now(timezone.utc) - timedelta(seconds=500)
    cur = ScriptedCursor(
        [[_wifi_baseline_row(last_seen=old_last_seen, expected_state="ignored")], []]
    )
    result = compute_baseline_comparison(
        cur, protocol="wifi", location_name="Lab", session_id=None, grace_seconds=180
    )
    assert len(result["missing"]) == 1
    assert result["missing"][0]["baseline_status"] == "ignored"


def test_baseline_comparison_bluetooth_uncertain_match_on_random_mac_vendor_overlap():
    baseline_rows = [
        {
            "id": "baseline-2",
            "stable_identity": "blefp:abc123",
            "expected_state": "expected",
            "vendor": "Acme",
            "last_seen": datetime.now(timezone.utc),
            "version": 1,
        }
    ]
    current_rows = [
        {
            "mac_address": "11:22:33:44:55:66",
            "stable_identity": "blefp:def456",
            "vendor": "Acme",
            "identity_confidence": "low",
            "observation_count": 5,
        }
    ]
    cur = ScriptedCursor([baseline_rows, current_rows])
    result = compute_baseline_comparison(
        cur, protocol="bluetooth", location_name="Lab", session_id=None, grace_seconds=300
    )
    assert result["items"][0]["baseline_status"] == "uncertain_match"
