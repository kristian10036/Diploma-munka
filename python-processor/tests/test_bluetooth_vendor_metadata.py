from datetime import datetime, timezone

from app.utils.parsing import normalize_bettercap_row, normalize_kismet_bluetooth_row


def test_bettercap_vendor_metadata_uses_company_identifier():
    normalized = normalize_bettercap_row(
        {
            "mac": "00:11:22:33:44:55",
            "vendor": "Example Vendor",
            "company_id": "0x004c",
            "manufacturer_data": "4c00112233",
        },
        datetime.now(timezone.utc),
    )

    assert normalized["vendor"] == "Example Vendor"
    assert normalized["vendor_resolution_method"] == "bluetooth_company_id"
    assert normalized["vendor_confidence"] == "high"
    assert normalized["bluetooth_company_id"] == 0x004C
    assert len(normalized["manufacturer_data_hash"]) == 64
    assert normalized["stable_identity"] == "00:11:22:33:44:55"
    assert normalized["identity_confidence"] == "high"


def test_random_address_vendor_is_low_confidence_not_oui_claim():
    normalized = normalize_kismet_bluetooth_row(
        {
            "kismet.device.base.macaddr": "aa:bb:cc:dd:ee:ff",
            "kismet.device.base.manuf": "OUI-like Vendor",
            "bluetooth.device.address_type": "random",
            "bluetooth.device.type": "BTLE",
        },
        datetime.now(timezone.utc),
    )

    assert normalized["vendor"] == "OUI-like Vendor"
    assert normalized["vendor_resolution_method"] == "kismet"
    assert normalized["vendor_confidence"] == "low"
    assert normalized["bluetooth_company_id"] is None
    assert normalized["stable_identity"].startswith("blefp:")
    assert normalized["identity_confidence"] == "unknown"


def test_random_address_with_service_gets_fingerprint_identity():
    normalized = normalize_bettercap_row(
        {
            "mac": "aa:bb:cc:dd:ee:ff",
            "name": "Sensor",
            "address_type": "random",
            "service_uuids": ["180f", "180a"],
        },
        datetime.now(timezone.utc),
    )

    assert normalized["stable_identity"].startswith("blefp:")
    assert normalized["identity_confidence"] == "low"


def test_unknown_vendor_string_stays_unknown():
    normalized = normalize_kismet_bluetooth_row(
        {
            "kismet.device.base.macaddr": "aa:bb:cc:dd:ee:ff",
            "kismet.device.base.manuf": "Unknown",
            "bluetooth.device.type": "BTLE",
        },
        datetime.now(timezone.utc),
    )

    assert normalized["vendor"] is None
    assert normalized["vendor_resolution_method"] == "unknown"
    assert normalized["vendor_confidence"] == "unknown"
