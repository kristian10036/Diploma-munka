from datetime import datetime, timezone

from app.utils.parsing import normalize_kismet_row


def test_kismet_wifi_ap_type_uses_device_role_not_ssid_only():
    row = {
        "kismet.device.base.macaddr": "aa:bb:cc:dd:ee:ff",
        "kismet.device.base.name": "Phone probe name",
        "kismet.device.base.type": "Wi-Fi Client",
        "dot11.device.last_probed_ssid": "Office",
    }

    normalized = normalize_kismet_row(row, datetime.now(timezone.utc))

    assert normalized["device_type"] == "client"
    assert normalized["stable_identity"] == "AA:BB:CC:DD:EE:FF"
    assert normalized["identity_confidence"] == "low"


def test_kismet_wifi_ap_type_from_access_point_role():
    row = {
        "kismet.device.base.macaddr": "11:22:33:44:55:66",
        "kismet.device.base.type": "Access Point",
        "dot11.device.last_beaconed_ssid": "Office",
    }

    normalized = normalize_kismet_row(row, datetime.now(timezone.utc))

    assert normalized["device_type"] == "AP"
    assert normalized["stable_identity"] == "11:22:33:44:55:66"
    assert normalized["identity_confidence"] == "high"


def test_kismet_wifi_mesh_and_adhoc_types():
    fallback = datetime.now(timezone.utc)

    assert (
        normalize_kismet_row(
            {"kismet.device.base.macaddr": "11:22:33:44:55:67", "dot11.device.role": "mesh node"},
            fallback,
        )["device_type"]
        == "bridge/mesh"
    )
    assert (
        normalize_kismet_row(
            {"kismet.device.base.macaddr": "11:22:33:44:55:68", "dot11.device.type": "IBSS"},
            fallback,
        )["device_type"]
        == "ad-hoc"
    )
