import json
import os
import urllib.error
import urllib.request

import pytest

BASE_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
pytestmark = pytest.mark.integration


def request(path: str, body: dict | None = None) -> tuple[int, dict]:
    payload = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if payload else {}
    try:
        with urllib.request.urlopen(
            urllib.request.Request(BASE_URL + path, data=payload, headers=headers), timeout=5
        ) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def test_ml_api_contract() -> None:
    status, ml_status = request("/api/ml/status")
    assert status == 200 and ml_status["available"] is True
    assert ml_status["model_version"] == "rf_rule_baseline_v1"
    assert ml_status["device"] == "cpu"
    assert "zigbee" in ml_status["withheld_classes"]

    status, registry = request("/api/ml/models")
    assert status == 200 and len(registry["models"]) == 4
    assert {model["model_type"] for model in registry["models"]} == {
        "rule_based_baseline",
        "classical_ml",
        "cnn",
        "onnx",
    }
    assert registry["ml_enabled"] is True
    assert registry["active_model_type"] == "rule"

    powers = [-95.0] * 101
    powers[50] = -30.0
    frame = {
        "schema_version": 1,
        "source_type": "mock",
        "session_id": "ml-contract-session",
        "start_frequency_hz": 2_400_000_000,
        "stop_frequency_hz": 2_500_000_000,
        "step_frequency_hz": 1_000_000,
        "num_points": 101,
        "power_unit": "dBm",
        "powers_dbm": powers,
    }
    status, classification = request("/api/ml/classify", {"frames": [frame]})
    assert status == 200
    assert classification["predicted_class"] == "narrowband_unknown"
    assert 0 <= classification["confidence"] <= 1
    assert classification["inference_time_ms"] >= 0

    status, rejected = request("/api/ml/classify", {"frames": [{"rssi": -42}]})
    assert status == 422 and "SpectrumFrame" in rejected["detail"]
