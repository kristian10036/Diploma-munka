from datetime import datetime, timezone

from app.config import BettercapSettings, KismetSettings
from app.routers.health_collectors import _merge_bluetooth_vendor_fields, _vendor_rank
from app.runtime import bluetooth_adapter_conflict_warning
from app.utils.parsing import normalize_bettercap_row


class FakeCursor:
    def __init__(self, existing):
        self.existing = existing

    def execute(self, query, parameters):
        self.query = query
        self.parameters = parameters

    def fetchone(self):
        return self.existing


def _row(vendor, method, confidence, company_id=None, manufacturer_hash=None):
    return {
        "vendor": vendor,
        "vendor_resolution_method": method,
        "vendor_confidence": confidence,
        "bluetooth_company_id": company_id,
        "manufacturer_data_hash": manufacturer_hash,
    }


def test_vendor_rank_ordering():
    assert _vendor_rank("bluetooth_company_id") > _vendor_rank("bettercap")
    assert _vendor_rank("bettercap") > _vendor_rank("kismet")
    assert _vendor_rank("kismet") > _vendor_rank("oui")
    assert _vendor_rank("oui") > _vendor_rank("unknown")
    assert _vendor_rank(None) == _vendor_rank("unknown") == 0


def test_merge_keeps_higher_priority_existing_vendor():
    existing = _row("Apple, Inc.", "bluetooth_company_id", "high", company_id=0x004C)
    cur = FakeCursor(existing)
    new_fields = _row("Generic OUI Vendor", "kismet", "medium")

    merged = _merge_bluetooth_vendor_fields(cur, "AA:BB:CC:DD:EE:FF", new_fields)

    assert merged["vendor"] == "Apple, Inc."
    assert merged["vendor_resolution_method"] == "bluetooth_company_id"
    assert merged["bluetooth_company_id"] == 0x004C


def test_merge_lets_higher_priority_new_vendor_win():
    existing = _row("Some Vendor", "kismet", "medium")
    cur = FakeCursor(existing)
    new_fields = _row("Apple, Inc.", "bettercap", "medium")

    merged = _merge_bluetooth_vendor_fields(cur, "AA:BB:CC:DD:EE:FF", new_fields)

    assert merged["vendor"] == "Apple, Inc."
    assert merged["vendor_resolution_method"] == "bettercap"


def test_merge_with_no_existing_row_uses_new_fields():
    cur = FakeCursor(None)
    new_fields = _row("Apple, Inc.", "bettercap", "medium")

    merged = _merge_bluetooth_vendor_fields(cur, "AA:BB:CC:DD:EE:FF", new_fields)

    assert merged is new_fields


def test_merge_does_not_downgrade_when_new_poll_has_no_vendor():
    existing = _row("Apple, Inc.", "bettercap", "medium")
    cur = FakeCursor(existing)
    new_fields = _row(None, "unknown", "unknown")

    merged = _merge_bluetooth_vendor_fields(cur, "AA:BB:CC:DD:EE:FF", new_fields)

    assert merged["vendor"] == "Apple, Inc."
    assert merged["vendor_resolution_method"] == "bettercap"


def test_bettercap_settings_defaults(monkeypatch):
    for key in (
        "BETTERCAP_INTEGRATION_ENABLED",
        "BETTERCAP_API_URL",
        "BETTERCAP_USERNAME",
        "BETTERCAP_PASSWORD",
        "BETTERCAP_API_TIMEOUT_SECONDS",
        "BETTERCAP_BLE_ENABLED",
        "BETTERCAP_BLE_INTERFACE",
        "BETTERCAP_POLL_INTERVAL_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = BettercapSettings.from_env()

    assert settings.enabled is False
    assert settings.api_url == "http://host.docker.internal:8081"
    assert settings.username == "user"
    assert settings.password == "pass"
    assert settings.timeout_seconds == 5.0
    assert settings.ble_enabled is True
    assert settings.ble_interface == "hci1"
    assert settings.poll_interval_seconds == 2.0
    assert settings.warnings == ()


def test_kismet_settings_bluetooth_interface_default(monkeypatch):
    monkeypatch.delenv("KISMET_BLUETOOTH_INTERFACE", raising=False)
    settings = KismetSettings.from_env()
    assert settings.bluetooth_interface == "hci0"


def test_adapter_conflict_warning_fires_on_same_interface(monkeypatch):
    monkeypatch.setenv("BETTERCAP_INTEGRATION_ENABLED", "true")
    monkeypatch.setenv("BETTERCAP_BLE_ENABLED", "true")
    monkeypatch.setenv("BETTERCAP_BLE_INTERFACE", "hci0")
    monkeypatch.setenv("KISMET_BLUETOOTH_INTERFACE", "hci0")

    kismet_settings = KismetSettings.from_env()
    bettercap_settings = BettercapSettings.from_env()

    warning = bluetooth_adapter_conflict_warning(kismet_settings, bettercap_settings)

    assert warning is not None
    assert "hci0" in warning


def test_adapter_conflict_warning_silent_on_different_interfaces(monkeypatch):
    monkeypatch.setenv("BETTERCAP_INTEGRATION_ENABLED", "true")
    monkeypatch.setenv("BETTERCAP_BLE_ENABLED", "true")
    monkeypatch.setenv("BETTERCAP_BLE_INTERFACE", "hci1")
    monkeypatch.setenv("KISMET_BLUETOOTH_INTERFACE", "hci0")

    kismet_settings = KismetSettings.from_env()
    bettercap_settings = BettercapSettings.from_env()

    assert bluetooth_adapter_conflict_warning(kismet_settings, bettercap_settings) is None


def test_adapter_conflict_warning_silent_when_bettercap_disabled(monkeypatch):
    monkeypatch.setenv("BETTERCAP_INTEGRATION_ENABLED", "false")
    monkeypatch.setenv("BETTERCAP_BLE_INTERFACE", "hci0")
    monkeypatch.setenv("KISMET_BLUETOOTH_INTERFACE", "hci0")

    kismet_settings = KismetSettings.from_env()
    bettercap_settings = BettercapSettings.from_env()

    assert bluetooth_adapter_conflict_warning(kismet_settings, bettercap_settings) is None


def test_normalize_bettercap_row_matches_real_api_session_ble_shape():
    """Shape captured from a real bettercap v2.41.7 GET /api/session/ble response."""
    row = {
        "last_seen": "2026-06-23T19:27:14.000000+00:00",
        "name": "",
        "mac": "54:07:af:a8:09:24",
        "alias": "",
        "vendor": "Apple, Inc.",
        "rssi": -92,
        "connectable": True,
        "flags": "",
        "services": [],
    }

    normalized = normalize_bettercap_row(row, datetime.now(timezone.utc))

    assert normalized["mac"] == "54:07:AF:A8:09:24"
    assert normalized["vendor"] == "Apple, Inc."
    assert normalized["vendor_resolution_method"] == "bettercap"
    assert normalized["rssi_dbm"] == -92.0


def test_normalize_bettercap_row_with_service_uuids_from_real_shape():
    row = {
        "mac": "aa:bb:cc:dd:ee:ff",
        "name": "Sensor Tag",
        "vendor": "Texas Instruments",
        "rssi": -70,
        "services": [{"uuid": "180f", "name": "Battery Service"}, {"uuid": "180a"}],
    }

    normalized = normalize_bettercap_row(row, datetime.now(timezone.utc))

    assert normalized["service_uuids"] == ["180f", "180a"]
    assert normalized["device_name"] == "Sensor Tag"
