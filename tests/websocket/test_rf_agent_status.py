import asyncio
import json
import os

import pytest
import websockets


URL = os.environ.get("RF_AGENT_STATUS_WS_URL", "ws://127.0.0.1:8765/ws/status")
pytestmark = pytest.mark.integration


async def main() -> None:
    async with websockets.connect(URL, open_timeout=5) as socket:
        first = json.loads(await asyncio.wait_for(socket.recv(), timeout=5))
        second = json.loads(await asyncio.wait_for(socket.recv(), timeout=5))
    assert {"mode", "source", "aaronia", "usrp", "sdrangel"} <= set(first)
    assert first["source"]["state"] in {
        "disabled", "not_initialized", "ready", "running", "paused", "stopped", "error"
    }
    assert first["aaronia"]["backend"] == "aaronia"
    assert second["mode"] == first["mode"]

def test_rf_agent_status_websocket_contract() -> None:
    asyncio.run(main())
