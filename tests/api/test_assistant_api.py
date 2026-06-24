import json
import os
import urllib.request

import pytest


BASE_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
pytestmark = pytest.mark.integration


def request(path: str, body: dict | None = None) -> dict:
    payload = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if payload else {}
    with urllib.request.urlopen(
        urllib.request.Request(BASE_URL + path, data=payload, headers=headers), timeout=10
    ) as response:
        assert response.status == 200
        return json.load(response)


def test_assistant_api_contract() -> None:
    status = request("/api/assistant/status")
    assert status["mode"] == "context_grounded_assistant"
    assert status["generation"]["implemented"] is True
    assert status["rag"]["implemented"] is True
    assert status["rag_status"] != "not_implemented"
    assert "context_grounded_assistant" in status["supported_modes"]
    assert "rag_assistant" in status["supported_modes"]

    result = request("/api/ask", {"question": "Adj összefoglalót a mérésekről és anomáliákról"})
    assert result["mode"] == "context_grounded_assistant"
    assert result["retrieval"] == "structured_sql"
    assert result["rag"] is False
    assert result["status"] == "ai_component_not_available"
    assert set(result["context"]) >= {"sessions", "wifi", "bluetooth", "peaks", "anomalies", "ml_status"}
    assert isinstance(result["source_records"], list)
    for records in result["context"].values():
        assert len(records) <= 10
