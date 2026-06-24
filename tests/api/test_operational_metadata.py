import json
import os
import time
import urllib.request

import pytest

BASE_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
pytestmark = pytest.mark.integration


def request(path: str, method: str = "GET", body: dict | None = None) -> dict:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if payload else {}
    with urllib.request.urlopen(
        urllib.request.Request(BASE_URL + path, data=payload, headers=headers, method=method),
        timeout=10,
    ) as response:
        assert response.status in (200, 201)
        return json.load(response)


def test_operational_metadata_api_contract() -> None:
    label = f"contract-marker-{int(time.time())}"
    marker = request(
        "/api/markers",
        "POST",
        {
            "frequency_hz": 2450000000,
            "power_dbm": -42.5,
            "label": label,
            "metadata": {"test": True},
        },
    )
    assert marker["label"] == label
    assert marker["frequency_hz"] == 2450000000

    markers = request("/api/markers?limit=20")
    assert any(item["id"] == marker["id"] for item in markers["items"])

    updated = request(
        f"/api/markers/{marker['id']}",
        "PATCH",
        {"label": label + "-updated", "category": "contract-test"},
    )
    assert updated["label"].endswith("-updated")

    audit = request("/api/audit/events?limit=50&event_type=spectrum.marker.created")
    assert any(item["entity_id"] == marker["id"] for item in audit["items"])

    known = request(
        "/api/known-signals",
        "POST",
        {
            "center_frequency_hz": 2450000000,
            "frequency_tolerance_hz": 10000,
            "bandwidth_hz": 20000000,
            "expected_power_min_dbm": -70,
            "expected_power_max_dbm": -30,
            "modulation": "OFDM",
            "source_type": "mock",
            "label": f"contract-known-{int(time.time())}",
            "suppress_alerts": True,
            "metadata": {"test": True},
        },
    )
    matched = request(
        "/api/known-signals/match",
        "POST",
        {
            "center_frequency_hz": 2450005000,
            "bandwidth_hz": 19000000,
            "power_dbm": -45,
            "modulation": "ofdm",
            "source_type": "mock",
        },
    )
    assert matched["matched"] is True and matched["suppress_alert"] is True

    changed = request(
        "/api/known-signals/match",
        "POST",
        {
            "center_frequency_hz": 2450005000,
            "bandwidth_hz": 1000000,
            "power_dbm": -10,
            "modulation": "AM",
            "source_type": "usrp",
        },
    )
    assert changed["suppress_alert"] is False

    archived_marker = request(f"/api/markers/{marker['id']}", "DELETE")
    assert archived_marker["archived_at"] is not None
    archived_signal = request(f"/api/known-signals/{known['id']}", "DELETE")
    assert archived_signal["archived_at"] is not None
