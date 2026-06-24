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


def test_rag_api_contract() -> None:
    wifi = request(
        "/api/rag/documents",
        {
            "title": "Wi-Fi mérési útmutató",
            "source": "rag-contract-wifi",
            "document_type": "test",
            "content": "Wi-Fi SSID és BSSID mérésnél rögzíteni kell a csatornát, frekvenciát és RSSI jelszintet. Wi-Fi SSID csatorna frekvencia.",
        },
    )
    bluetooth = request(
        "/api/rag/documents",
        {
            "title": "Bluetooth mérési útmutató",
            "source": "rag-contract-bluetooth",
            "document_type": "test",
            "content": "Bluetooth BLE vizsgálatnál a MAC-cím, eszköznév és service UUID mezők szükségesek.",
        },
    )
    assert wifi["chunk_count"] == 1 and bluetooth["chunk_count"] == 1

    status = request("/api/rag/status")
    assert status["available"] is True
    assert status["vector_index"] == "pgvector_hnsw_cosine"
    assert status["indexed_embeddings"] >= 2

    retrieval = request("/api/rag/retrieve", {"query": "Wi-Fi SSID csatorna frekvencia", "top_k": 2})
    assert len(retrieval["items"]) == 2
    assert retrieval["items"][0]["source"] == "rag-contract-wifi"
    assert retrieval["items"][0]["similarity"] > retrieval["items"][1]["similarity"]
    assert retrieval["source_records"][0]["record_type"] == "document_chunk"

    answer = request("/api/ask", {"question": "Mit ír a dokumentáció a Wi-Fi SSID csatorna méréséről?"})
    assert answer["rag"] is True
    assert answer["mode"] == "rag_assistant"
    assert answer["retrieval"] == "structured_sql_and_vector_top_k"
    assert answer["status"] == "ai_component_not_available"
    assert any(source["record_type"] == "document_chunk" for source in answer["source_records"])
