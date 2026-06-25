import json
import os
import urllib.error
import urllib.request

import pytest

BASE_URL = os.environ.get("RF_AGENT_URL", "http://127.0.0.1:8765").rstrip("/")
pytestmark = pytest.mark.integration


def request(path: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    try:
        with urllib.request.urlopen(
            urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method),
            timeout=5,
        ) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def test_rf_agent_rest_contract() -> None:
    status, health = request("/health")
    assert status == 200 and health["status"] == "ok"
    assert health["source"]["backend"] in {"mock", "replay", "aaronia", "usrp", "hackrf"}

    status, before = request("/aaronia/status")
    assert status == 200 and before["backend"] == "aaronia"

    status, probe = request("/aaronia/probe", "POST")
    assert status == 200
    assert probe["probe_result"] in {
        "sdk_not_found",
        "sdk_symbol_missing",
        "library_load_failed",
        "library_sigill",
        "library_sigsegv",
        "sdk_init_failed",
        "sdk_ready",
        "probe_timeout",
        "unknown_failure",
    }

    status, usrp = request("/usrp/status")
    assert status == 200 and "available" in usrp

    status, hackrf = request("/hackrf/status")
    assert status == 200 and hackrf["data_plane"] == "soapy_iq_spectrum_native_audio"

    status, sdrangel = request("/sdrangel/status")
    assert status == 200
    assert sdrangel["control_plane"] in {"disabled", "configured", "ready", "unreachable"}
    assert sdrangel["data_plane"] == "not_configured"

    status, recording_status = request("/recordings/status")
    assert status == 200 and set(recording_status) >= {"active", "frame_count", "recording_id"}

    status, missing_recording = request("/recordings/__contract_missing__")
    assert status == 404
    assert missing_recording["error"]["code"] == "RECORDING_NOT_FOUND"

    status, error = request("/__contract_missing__")
    assert status == 404
    assert set(error["error"]) == {"code", "message", "details"}
    assert error["error"]["code"] == "ENDPOINT_NOT_FOUND"


def test_rf_agent_viewport_contract() -> None:
    status, capabilities = request("/capabilities")
    assert (
        status == 200
        and "viewport_control" in capabilities
        and "maximum_spectrum_points" in capabilities
    )

    status, invalid = request(
        "/source/viewport",
        "POST",
        {
            "request_id": "contract-test-invalid",
            "mode": "continuous",
            "center_frequency_hz": 433920000,
            "span_hz": 2000000,
            "maximum_points": 4800,
        },
    )
    assert status == 422
    assert invalid["error"]["code"] == "INVALID_VIEWPORT_REQUEST"

    status, result = request(
        "/source/viewport",
        "POST",
        {
            "request_id": "contract-test-valid",
            "mode": "sweep",
            "center_frequency_hz": 433920000,
            "span_hz": 2000000,
            "maximum_points": 4800,
        },
    )
    if capabilities["viewport_control"]:
        assert status == 200
        assert result["status"] in {"accepted", "constrained"}
        assert set(result) >= {
            "schema_version",
            "request_id",
            "status",
            "mode",
            "center_frequency_hz",
            "span_hz",
            "start_frequency_hz",
            "stop_frequency_hz",
            "step_frequency_hz",
            "num_points",
            "source_type",
            "hardware_execution",
        }
        assert result["num_points"] <= capabilities["maximum_spectrum_points"]
    else:
        assert status == 422
        assert result["error"]["code"] == "VIEWPORT_NOT_SUPPORTED"
