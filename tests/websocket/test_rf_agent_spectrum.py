import asyncio
import json
import os

import pytest
import websockets


URL = os.environ.get("RF_AGENT_WS_URL", "ws://127.0.0.1:8765/ws/spectrum")
pytestmark = pytest.mark.integration
REQUIRED = {
    "schema_version",
    "sensor_id",
    "source_type",
    "source_device",
    "session_id",
    "timestamp",
    "sequence",
    "start_frequency_hz",
    "stop_frequency_hz",
    "step_frequency_hz",
    "center_frequency_hz",
    "sample_rate_hz",
    "rbw_hz",
    "num_points",
    "power_unit",
    "powers_dbm",
    "flags",
    "metadata",
}


async def main() -> None:
    async with websockets.connect(URL, open_timeout=5, max_size=4 * 1024 * 1024) as socket:
        first = json.loads(await asyncio.wait_for(socket.recv(), timeout=5))
        second = json.loads(await asyncio.wait_for(socket.recv(), timeout=5))

    assert REQUIRED <= set(first)
    assert "frequencies_hz" not in first
    assert first["schema_version"] == 1 and first["power_unit"] == "dBm"
    assert len(first["powers_dbm"]) == first["num_points"]
    assert first["stop_frequency_hz"] == (
        first["start_frequency_hz"]
        + first["step_frequency_hz"] * (first["num_points"] - 1)
    )
    assert second["sequence"] > first["sequence"]
    if first["source_type"] in {"mock", "replay"}:
        assert first["metadata"]["is_simulated"] is True

def test_rf_agent_spectrum_websocket_contract() -> None:
    asyncio.run(main())
