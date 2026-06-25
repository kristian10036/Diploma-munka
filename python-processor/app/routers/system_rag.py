from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.assistant import (
    build_grounded_prompt,
    call_ollama,
    collect_sql_context,
    is_mac_inventory_question,
    model_is_installed,
)
from app.db import get_db
from app.rag import database_rag_status, index_document, retrieve_chunks
from app.rf_agent_client import rf_agent_status
from app.runtime import (
    ASSISTANT_SETTINGS,
    BETTERCAP_SETTINGS,
    DATABASE_URL,
    KISMET_SETTINGS,
    ML_CLASSIFIER,
    RAG_SETTINGS,
    RF_AGENT_SETTINGS,
)
from app.schemas import AskRequest, RagDocumentRequest, RagRetrieveRequest
from app.services.persistence import fetch_repeated_macs

router = APIRouter()


@router.get("/api/system/status")
def system_status():
    database = {"configured": bool(DATABASE_URL), "available": False, "status": "not_configured"}
    rag: dict[str, Any] = {
        "implemented": True,
        "enabled": RAG_SETTINGS.enabled,
        "available": False,
        "status": "database_unavailable",
    }
    try:
        with get_db() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 AS ok")
                cursor.fetchone()
            database = {"configured": True, "available": True, "status": "ready"}
            rag = {
                "implemented": True,
                "enabled": RAG_SETTINGS.enabled,
                **database_rag_status(connection, RAG_SETTINGS),
            }
    except HTTPException as exc:
        database = {
            "configured": bool(DATABASE_URL),
            "available": False,
            "status": "unreachable",
            "error": str(exc.detail),
        }
    return {
        "status": "ok",
        "backend": {"available": True, "status": "ready"},
        "database": database,
        "rf_agent": rf_agent_status(RF_AGENT_SETTINGS),
        "ml": ML_CLASSIFIER.status(),
        "assistant": ASSISTANT_SETTINGS.status(),
        "rag": rag,
        "kismet": {"implemented": True, "enabled": KISMET_SETTINGS.enabled},
        "bettercap": {"implemented": True, "enabled": BETTERCAP_SETTINGS.enabled},
    }


@router.get("/api/rag/status")
def rag_status():
    with get_db() as connection:
        return database_rag_status(connection, RAG_SETTINGS)


@router.post("/api/rag/documents")
def rag_index_document(request: RagDocumentRequest):
    title = request.title.strip()
    content = request.content.strip()
    if not title or len(title) > 500:
        raise HTTPException(status_code=422, detail="document title must contain 1-500 characters")
    if not content or len(content) > 2_000_000:
        raise HTTPException(
            status_code=422, detail="document content must contain 1-2000000 characters"
        )
    if not RAG_SETTINGS.configured():
        raise HTTPException(status_code=503, detail="rag_component_not_available")
    try:
        with get_db() as connection:
            return index_document(
                connection,
                RAG_SETTINGS,
                title,
                content,
                request.source,
                request.document_type,
                request.metadata or {},
            )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/rag/retrieve")
def rag_retrieve(request: RagRetrieveRequest):
    query = request.query.strip()
    if not query or len(query) > 2000:
        raise HTTPException(status_code=422, detail="query must contain 1-2000 characters")
    if not RAG_SETTINGS.configured():
        raise HTTPException(status_code=503, detail="rag_component_not_available")
    try:
        with get_db() as connection:
            items = retrieve_chunks(connection, RAG_SETTINGS, query, request.top_k)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "query": query,
        "top_k": request.top_k or RAG_SETTINGS.default_top_k,
        "embedding_model": RAG_SETTINGS.embedding_model,
        "items": items,
        "source_records": [
            {
                "record_type": "document_chunk",
                "record_id": item["chunk_id"],
                "document_id": item["document_id"],
            }
            for item in items
        ],
    }


@router.get("/api/assistant/status")
def assistant_status():
    generation = ASSISTANT_SETTINGS.live_status()
    with get_db() as connection:
        rag = database_rag_status(connection, RAG_SETTINGS)
    installed_models = set(generation.get("installed_models", []))
    embedding_installed = model_is_installed(RAG_SETTINGS.embedding_model, installed_models)
    if RAG_SETTINGS.provider == "ollama" and not embedding_installed:
        rag = {**rag, "available": False, "status": "embedding_model_not_installed"}
    # Structured fields are the source of truth. Legacy flat fields remain for
    # frontend/backward compatibility.
    return {
        **generation,
        "generation": generation,
        "rag": {
            "implemented": True,
            "enabled": RAG_SETTINGS.enabled,
            **rag,
            "embedding_model_installed": embedding_installed,
        },
        "rag_available": rag["available"],
        "rag_status": rag["status"],
        "rag_embedding_model": rag["embedding_model"],
        "rag_indexed_embeddings": rag["indexed_embeddings"],
        "supported_modes": ["context_grounded_assistant", "rag_assistant"],
    }


@router.post("/api/ask")
def ask_database(request: AskRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="A kerdes nem lehet ures.")
    if len(question) > 2000:
        raise HTTPException(status_code=413, detail="A kerdes legfeljebb 2000 karakter lehet.")

    normalized = question.casefold()
    if is_mac_inventory_question(question):
        with get_db() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT domain, mac_address, MAX(last_seen) AS last_seen
                    FROM (
                        SELECT 'wifi' AS domain, UPPER(TRIM(bssid)) AS mac_address,
                               COALESCE(observed_at, time) AS last_seen
                        FROM wifi_observations
                        WHERE bssid IS NOT NULL AND TRIM(bssid) <> ''
                        UNION ALL
                        SELECT 'bluetooth' AS domain, UPPER(TRIM(mac_address)) AS mac_address,
                               time AS last_seen
                        FROM bluetooth_observations
                        WHERE mac_address IS NOT NULL AND TRIM(mac_address) <> ''
                    ) observed_macs
                    GROUP BY domain, mac_address
                    ORDER BY domain, mac_address
                    """
                )
                mac_inventory = [dict(row) for row in cursor.fetchall()]
        wifi_macs = [row["mac_address"] for row in mac_inventory if row["domain"] == "wifi"]
        bluetooth_macs = [
            row["mac_address"] for row in mac_inventory if row["domain"] == "bluetooth"
        ]
        unique_macs = {row["mac_address"] for row in mac_inventory}
        answer_sections = [
            f"Összesen {len(unique_macs)} különböző MAC-cím látható az adatbázisban.",
            f"Wi-Fi BSSID-k ({len(wifi_macs)}):\n" + "\n".join(f"- {mac}" for mac in wifi_macs),
            f"Bluetooth MAC-címek ({len(bluetooth_macs)}):\n"
            + "\n".join(f"- {mac}" for mac in bluetooth_macs),
        ]
        return {
            "mode": "structured_sql_answer",
            "retrieval": "structured_sql_unique_mac_inventory",
            "rag": False,
            "rag_status": "not_used",
            "question": question,
            "context": {"visible_macs": mac_inventory},
            "source_records": [
                {
                    "record_type": f"{row['domain']}_mac",
                    "record_id": row["mac_address"],
                    "timestamp": str(row["last_seen"]) if row["last_seen"] else None,
                }
                for row in mac_inventory
            ],
            "available": True,
            "status": "ok",
            "answer": "\n\n".join(answer_sections),
        }
    bluetooth_mac_count_question = (
        "bluetooth" in normalized
        and "mac" in normalized
        and any(term in normalized for term in ("hány", "hany", "mennyi", "darab"))
    )
    bluetooth_summary = None
    rag_items = []
    rag_error = None
    with get_db() as connection:
        context, source_records = collect_sql_context(
            connection, question, ASSISTANT_SETTINGS.max_context_records
        )
        if bluetooth_mac_count_question:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(DISTINCT UPPER(TRIM(mac_address))) AS unique_mac_count,
                           COUNT(*) AS observation_count
                    FROM bluetooth_observations
                    WHERE mac_address IS NOT NULL AND TRIM(mac_address) <> ''
                    """
                )
                bluetooth_summary = dict(cursor.fetchone())
            context["bluetooth_summary"] = [bluetooth_summary]
        if RAG_SETTINGS.configured():
            try:
                rag_items = retrieve_chunks(connection, RAG_SETTINGS, question)
            except Exception as exc:
                rag_error = f"rag_retrieval_unavailable: {exc}"
    if rag_items:
        context["document_chunks"] = rag_items
        source_records.extend(
            {
                "record_type": "document_chunk",
                "record_id": item["chunk_id"],
                "document_id": item["document_id"],
            }
            for item in rag_items
        )
    if any(term in normalized for term in ("mac", "mac-cim", "maccim")) and any(
        term in normalized for term in ("tobb hely", "tobb helyszin", "ismetlod", "elofordul")
    ):
        repeated = fetch_repeated_macs(2)
        context["repeated_macs"] = repeated
        source_records.extend(
            {"record_type": "repeated_macs", "record_id": str(item["mac_address"])}
            for item in repeated
        )
    context["ml_status"] = [ML_CLASSIFIER.status()]
    rag_used = bool(rag_items)
    base = {
        "mode": "rag_assistant" if rag_used else "context_grounded_assistant",
        "retrieval": "structured_sql_and_vector_top_k" if rag_used else "structured_sql",
        "rag": rag_used,
        "rag_status": "used" if rag_used else (rag_error or "not_used"),
        "question": question,
        "context": context,
        "source_records": source_records,
    }
    if bluetooth_summary is not None:
        unique_count = int(bluetooth_summary["unique_mac_count"])
        observation_count = int(bluetooth_summary["observation_count"])
        return {
            **base,
            "mode": "structured_sql_answer",
            "available": True,
            "status": "ok",
            "answer": (
                f"{unique_count} különböző Bluetooth-eszközhöz tartozó MAC-címet látok "
                f"az adatbázisban, összesen {observation_count} megfigyelési rekordban."
            ),
        }
    generation_status = ASSISTANT_SETTINGS.status()
    if not generation_status["available"]:
        return {
            **base,
            "available": False,
            "status": "ai_component_not_available",
            "generation_status": generation_status["status"],
        }
    prompt = build_grounded_prompt(question, context, source_records)
    try:
        answer = call_ollama(ASSISTANT_SETTINGS, prompt)
    except RuntimeError as exc:
        return {**base, "available": False, "status": "ollama_unavailable", "error": str(exc)}
    return {
        **base,
        "available": True,
        "status": "ok",
        "model": ASSISTANT_SETTINGS.model,
        "answer": answer,
    }
