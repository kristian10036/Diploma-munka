from datetime import datetime, timezone

from app.routers.anomalies_alerts import _wifi_security_event
from app.utils.parsing import normalize_kismet_alert_row


def test_wifi_security_event_keeps_unknown_macs_null():
    row = {
        "id": "alert-1",
        "created_at": datetime.now(timezone.utc),
        "last_seen_at": datetime.now(timezone.utc),
        "severity": "warning",
        "status": "open",
        "source": "kismet_eventbus",
        "code": "deauthentication_flood",
        "message": "Kismet deauth alert",
        "occurrence_count": 3,
        "metadata": {
            "frame_type": "deauthentication",
            "reason_code": 7,
            "evidence": {"confidence": "low"},
        },
    }

    event = _wifi_security_event(row)

    assert event["transmitter_label"] == "Feltételezett keretküldő"
    assert event["suspected_transmitter_mac"] is None
    assert event["destination_mac"] is None
    assert event["frame_type"] == "deauthentication"
    assert event["reason_code"] == 7
    assert event["confidence"] == "low"
    assert event["event_count"] == 3


def test_wifi_security_event_maps_available_kismet_fields():
    row = {
        "id": "alert-2",
        "created_at": datetime.now(timezone.utc),
        "last_seen_at": datetime.now(timezone.utc),
        "severity": "critical",
        "status": "acknowledged",
        "source": "kismet_eventbus",
        "code": "ssid_spoof",
        "message": "SSID spoof suspicion",
        "occurrence_count": 1,
        "metadata": {
            "suspected_transmitter_mac": "00:11:22:33:44:55",
            "victim_mac": "66:77:88:99:AA:BB",
            "bssid": "00:11:22:33:44:55",
            "ssid": "Office",
            "channel": 6,
            "frequency_hz": 2437000000,
            "rssi_dbm": -42,
            "confidence": "medium",
        },
    }

    event = _wifi_security_event(row)

    assert event["alert_type"] == "ssid_spoof"
    assert event["suspected_transmitter_mac"] == "00:11:22:33:44:55"
    assert event["destination_mac"] == "66:77:88:99:AA:BB"
    assert event["ssid"] == "Office"
    assert event["review_state"] == "acknowledged"


def test_kismet_alert_normalizer_preserves_only_available_macs():
    normalized = normalize_kismet_alert_row(
        {
            "kismet.alert.class": "DEAUTHFLOOD",
            "kismet.alert.text": "Deauthentication flood",
            "severity": "high",
            "bssid": "00:11:22:33:44:55",
            "ssid": "Office",
            "frame_type": "deauthentication",
            "reason_code": 7,
            "channel": 6,
            "rssi_dbm": -55,
        },
        datetime.now(timezone.utc),
    )

    assert normalized["alert_type"] == "DEAUTHFLOOD"
    assert normalized["severity"] == "error"
    assert normalized["suspected_transmitter_mac"] is None
    assert normalized["destination_mac"] is None
    assert normalized["bssid"] == "00:11:22:33:44:55"
    assert normalized["confidence"] == "low"
