import json
import os
import urllib.error
import urllib.request

import pytest


BASE_URL = os.environ.get("RF_AGENT_URL", "http://127.0.0.1:8765").rstrip("/")
pytestmark = pytest.mark.integration


def request(path: str, method: str = "GET") -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(
            urllib.request.Request(BASE_URL + path, method=method), timeout=5
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
