from datetime import datetime, timedelta, timezone

from app.routers.health_collectors import _bluetooth_history_needed, _wifi_history_needed


class FakeCursor:
    def __init__(self, previous):
        self.previous = previous
        self.query = None
        self.parameters = None

    def execute(self, query, parameters):
        self.query = query
        self.parameters = parameters

    def fetchone(self):
        return self.previous


def test_wifi_history_skips_unchanged_snapshot_inside_heartbeat():
    now = datetime.now(timezone.utc)
    previous = {
        "observed_at": now,
        "ssid": "Office",
        "channel": 6,
        "frequency_hz": 2437000000,
        "signal_dbm": -55.0,
        "encryption": "WPA2",
        "device_type": "AP",
        "stable_identity": "AA:BB:CC:DD:EE:FF",
        "identity_confidence": "high",
    }
    fields = {
        "observed_at": now + timedelta(seconds=2),
        "ssid": "Office",
        "channel": 6,
        "frequency_hz": 2437000000,
        "signal_dbm": -55.0,
        "encryption": "WPA2",
        "device_type": "AP",
        "stable_identity": "AA:BB:CC:DD:EE:FF",
        "identity_confidence": "high",
    }

    assert (
        _wifi_history_needed(FakeCursor(previous), None, "Lab", "AA:BB:CC:DD:EE:FF", fields)
        is False
    )


def test_wifi_history_uses_rssi_delta_threshold():
    now = datetime.now(timezone.utc)
    previous = {
        "observed_at": now,
        "ssid": "Office",
        "channel": 6,
        "frequency_hz": 2437000000,
        "signal_dbm": -55.0,
        "encryption": "WPA2",
        "device_type": "AP",
        "stable_identity": "AA:BB:CC:DD:EE:FF",
        "identity_confidence": "high",
    }
    base_fields = {
        "observed_at": now + timedelta(seconds=2),
        "ssid": "Office",
        "channel": 6,
        "frequency_hz": 2437000000,
        "encryption": "WPA2",
        "device_type": "AP",
        "stable_identity": "AA:BB:CC:DD:EE:FF",
        "identity_confidence": "high",
    }

    assert (
        _wifi_history_needed(
            FakeCursor(previous),
            None,
            "Lab",
            "AA:BB:CC:DD:EE:FF",
            {**base_fields, "signal_dbm": -57.0},
        )
        is False
    )
    assert (
        _wifi_history_needed(
            FakeCursor(previous),
            None,
            "Lab",
            "AA:BB:CC:DD:EE:FF",
            {**base_fields, "signal_dbm": -60.0},
        )
        is True
    )


def test_wifi_history_heartbeat_creates_sample():
    now = datetime.now(timezone.utc)
    previous = {
        "observed_at": now,
        "ssid": "Office",
        "channel": 6,
        "frequency_hz": 2437000000,
        "signal_dbm": -55.0,
        "encryption": "WPA2",
        "device_type": "AP",
        "stable_identity": "AA:BB:CC:DD:EE:FF",
        "identity_confidence": "high",
    }
    fields = {
        "observed_at": now + timedelta(seconds=11),
        "ssid": "Office",
        "channel": 6,
        "frequency_hz": 2437000000,
        "signal_dbm": -55.0,
        "encryption": "WPA2",
        "device_type": "AP",
        "stable_identity": "AA:BB:CC:DD:EE:FF",
        "identity_confidence": "high",
    }

    assert (
        _wifi_history_needed(FakeCursor(previous), None, "Lab", "AA:BB:CC:DD:EE:FF", fields) is True
    )


def test_bluetooth_history_skips_unchanged_snapshot_inside_heartbeat():
    now = datetime.now(timezone.utc)
    previous = {
        "observed_at": now,
        "device_name": "Beacon",
        "rssi_dbm": -62.0,
        "vendor": "Example",
        "service_uuids": ["180f"],
        "address_type": "public",
        "bluetooth_type": "ble",
        "vendor_resolution_method": "kismet",
        "vendor_confidence": "medium",
        "bluetooth_company_id": None,
        "manufacturer_data_hash": None,
        "stable_identity": "AA:BB:CC:DD:EE:FF",
        "identity_confidence": "high",
    }
    fields = {
        "observed_at": now + timedelta(seconds=2),
        "device_name": "Beacon",
        "rssi_dbm": -63.0,
        "vendor": "Example",
        "service_uuids": ["180f"],
        "address_type": "public",
        "bluetooth_type": "ble",
        "vendor_resolution_method": "kismet",
        "vendor_confidence": "medium",
        "bluetooth_company_id": None,
        "manufacturer_data_hash": None,
        "stable_identity": "AA:BB:CC:DD:EE:FF",
        "identity_confidence": "high",
    }

    assert (
        _bluetooth_history_needed(FakeCursor(previous), None, "Lab", "AA:BB:CC:DD:EE:FF", fields)
        is False
    )
