from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

EMBEDDING_DIMENSIONS = 768


def embedding_dimensions(provider: str, model: str) -> int:
    if provider == "ollama" and model.casefold().split(":", 1)[0] == "bge-m3":
        return 1024
    return EMBEDDING_DIMENSIONS


@dataclass(frozen=True)
class RagSettings:
    enabled: bool
    provider: str
    embedding_model: str
    ollama_url: str
    timeout_seconds: float
    chunk_characters: int
    chunk_overlap: int
    default_top_k: int

    @classmethod
    def from_env(cls) -> "RagSettings":
        enabled = os.getenv("RAG_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
        provider = os.getenv("RAG_EMBEDDING_PROVIDER", "local_hash").strip().lower()
        model = os.getenv(
            "RAG_EMBEDDING_MODEL",
            "local-feature-hash-v1" if provider == "local_hash" else "embeddinggemma",
        ).strip()
        try:
            timeout = max(1.0, min(600.0, float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300"))))
        except ValueError:
            timeout = 20.0
        try:
            chunk_size = max(256, min(4000, int(os.getenv("RAG_CHUNK_CHARACTERS", "1200"))))
            overlap = max(0, min(chunk_size // 2, int(os.getenv("RAG_CHUNK_OVERLAP", "200"))))
            top_k = max(1, min(20, int(os.getenv("RAG_TOP_K", "5"))))
        except ValueError:
            chunk_size, overlap, top_k = 1200, 200, 5
        return cls(
            enabled,
            provider,
            model,
            os.getenv("OLLAMA_URL", "http://ollama:11434").rstrip("/"),
            timeout,
            chunk_size,
            overlap,
            top_k,
        )

    def configured(self) -> bool:
        return (
            self.enabled
            and self.provider in {"local_hash", "ollama"}
            and bool(self.embedding_model)
        )


def chunk_text(content: str, max_characters: int = 1200, overlap: int = 200) -> list[str]:
    text = re.sub(r"\r\n?", "\n", content).strip()
    if not text:
        raise ValueError("document content is empty")
    if max_characters < 64 or overlap < 0 or overlap >= max_characters:
        raise ValueError("invalid chunk configuration")
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_characters)
        if end < len(text):
            boundary = max(
                text.rfind("\n", start + max_characters // 2, end),
                text.rfind(" ", start + max_characters // 2, end),
            )
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def local_hash_embeddings(
    texts: list[str], dimensions: int = EMBEDDING_DIMENSIONS
) -> list[list[float]]:
    if dimensions < 64 or not texts:
        raise ValueError("invalid embedding request")
    vectors: list[list[float]] = []
    for text in texts:
        tokens = re.findall(r"[\wáéíóöőúüű]+", text.casefold(), flags=re.UNICODE)
        features = tokens + [f"{left}_{right}" for left, right in zip(tokens, tokens[1:])]
        vector = [0.0] * dimensions
        for feature in features:
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            raise ValueError("text has no embeddable tokens")
        vectors.append([value / norm for value in vector])
    return vectors


def ollama_embeddings(settings: RagSettings, texts: list[str]) -> list[list[float]]:
    if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("invalid embedding request")
    expected_dimensions = embedding_dimensions(settings.provider, settings.embedding_model)
    request = urllib.request.Request(
        settings.ollama_url + "/api/embed",
        data=json.dumps(
            {
                "model": settings.embedding_model,
                "input": texts,
                "truncate": True,
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    value = None
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=settings.timeout_seconds) as response:
                value = json.load(response)
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read(4096).decode("utf-8", "replace")
            if exc.code == 404 or "model" in detail.casefold() and "not found" in detail.casefold():
                raise RuntimeError("embedding_model_not_installed") from exc
            last_error = exc
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = exc
        if attempt == 0:
            time.sleep(0.1)
    if value is None:
        raise RuntimeError(f"embedding_provider_unavailable: {last_error}") from last_error
    if not isinstance(value, dict):
        raise RuntimeError("embedding_provider_invalid_response")
    embeddings = value.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
        raise RuntimeError("embedding_provider_invalid_response")
    try:
        result = [[float(item) for item in vector] for vector in embeddings]
    except (TypeError, ValueError) as exc:
        raise RuntimeError("embedding_provider_invalid_response") from exc
    if any(
        len(vector) != expected_dimensions or not all(math.isfinite(item) for item in vector)
        for vector in result
    ):
        raise RuntimeError("embedding_provider_invalid_dimensions")
    return result


def embed_texts(settings: RagSettings, texts: list[str]) -> list[list[float]]:
    if not settings.configured():
        raise RuntimeError("rag_component_not_available")
    if settings.provider == "local_hash":
        return local_hash_embeddings(texts)
    return ollama_embeddings(settings, texts)


def vector_literal(vector: list[float], dimensions: int = EMBEDDING_DIMENSIONS) -> str:
    if len(vector) != dimensions or not all(math.isfinite(value) for value in vector):
        raise ValueError("invalid embedding vector")
    return "[" + ",".join(f"{value:.9g}" for value in vector) + "]"


def index_document(
    connection: Any,
    settings: RagSettings,
    title: str,
    content: str,
    source: str | None,
    document_type: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    chunks = chunk_text(content, settings.chunk_characters, settings.chunk_overlap)
    embeddings = embed_texts(settings, chunks)
    dimensions = embedding_dimensions(settings.provider, settings.embedding_model)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO documents (title, document_type, source, content, metadata)
            VALUES (%s, %s, %s, %s, %s::jsonb) RETURNING id::text
            """,
            (title, document_type, source, content, json.dumps(metadata)),
        )
        document_id = cursor.fetchone()["id"]
        chunk_ids = []
        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            cursor.execute(
                """
                INSERT INTO document_chunks (document_id, chunk_index, content, metadata)
                VALUES (%s, %s, %s, %s::jsonb) RETURNING id::text
                """,
                (document_id, index, chunk, json.dumps({"source": source})),
            )
            chunk_id = cursor.fetchone()["id"]
            chunk_ids.append(chunk_id)
            cursor.execute(
                """
                INSERT INTO embeddings
                  (chunk_id, embedding_provider, embedding_model, dimensions, embedding_vector,
                   content_sha256, updated_at)
                VALUES (%s, %s, %s, %s, %s::vector, %s, now())
                ON CONFLICT (chunk_id, embedding_provider, embedding_model) DO UPDATE SET
                  embedding_provider = EXCLUDED.embedding_provider,
                  dimensions = EXCLUDED.dimensions,
                  embedding_vector = EXCLUDED.embedding_vector,
                  content_sha256 = EXCLUDED.content_sha256,
                  updated_at = now()
                """,
                (
                    chunk_id,
                    settings.provider,
                    settings.embedding_model,
                    dimensions,
                    vector_literal(embedding, dimensions),
                    hashlib.sha256(chunk.encode()).hexdigest(),
                ),
            )
    connection.commit()
    return {
        "document_id": document_id,
        "chunk_ids": chunk_ids,
        "chunk_count": len(chunk_ids),
        "embedding_model": settings.embedding_model,
    }


def retrieve_chunks(
    connection: Any, settings: RagSettings, query: str, top_k: int | None = None
) -> list[dict[str, Any]]:
    limit = max(1, min(20, top_k or settings.default_top_k))
    dimensions = embedding_dimensions(settings.provider, settings.embedding_model)
    query_vector = vector_literal(embed_texts(settings, [query])[0], dimensions)
    query_sql = f"""
            SELECT chunk.id::text AS chunk_id, document.id::text AS document_id,
                   document.title, document.source, chunk.chunk_index, chunk.content,
                   chunk.metadata,
                   1 - (embedding.embedding_vector::vector({dimensions})
                        <=> %s::vector({dimensions})) AS similarity
            FROM embeddings embedding
            JOIN document_chunks chunk ON chunk.id = embedding.chunk_id
            JOIN documents document ON document.id = chunk.document_id
            WHERE embedding.embedding_provider = %s AND embedding.embedding_model = %s
              AND embedding.dimensions = %s AND embedding.embedding_vector IS NOT NULL
            ORDER BY embedding.embedding_vector::vector({dimensions}) <=> %s::vector({dimensions})
            LIMIT %s
            """
    with connection.cursor() as cursor:
        cursor.execute(
            query_sql,
            (
                query_vector,
                settings.provider,
                settings.embedding_model,
                dimensions,
                query_vector,
                limit,
            ),
        )
        return [
            {
                **dict(row),
                "similarity": float(row["similarity"]),
            }
            for row in cursor.fetchall()
        ]


def database_rag_status(connection: Any, settings: RagSettings) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') AS vector_enabled"
        )
        vector_enabled = bool(cursor.fetchone()["vector_enabled"])
        dimensions = embedding_dimensions(settings.provider, settings.embedding_model)
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = %s) AS index_enabled",
            (f"idx_embeddings_vector_hnsw_{dimensions}",),
        )
        index_enabled = bool(cursor.fetchone()["index_enabled"])
        cursor.execute(
            "SELECT COUNT(*) AS count FROM embeddings WHERE embedding_vector IS NOT NULL"
        )
        embedding_count = int(cursor.fetchone()["count"])
        cursor.execute("SELECT COUNT(*) AS count FROM document_chunks")
        chunk_count = int(cursor.fetchone()["count"])
        cursor.execute(
            "SELECT COUNT(*) AS count FROM embeddings WHERE embedding_provider = %s "
            "AND embedding_model = %s AND dimensions = %s AND embedding_vector IS NOT NULL",
            (settings.provider, settings.embedding_model, dimensions),
        )
        compatible_count = int(cursor.fetchone()["count"])
    configured = settings.configured()
    available = configured and vector_enabled and index_enabled
    if not settings.enabled:
        status = "disabled"
    elif settings.provider not in {"local_hash", "ollama"} or not settings.embedding_model:
        status = "not_configured"
    elif not vector_enabled or not index_enabled:
        status = "database_not_ready"
    elif compatible_count == 0:
        status = "ready_empty"
    else:
        status = "ready"
    return {
        "enabled": settings.enabled,
        "configured": configured,
        "available": available,
        "status": status,
        "provider": settings.provider,
        "embedding_model": settings.embedding_model,
        "dimensions": dimensions,
        "vector_extension": vector_enabled,
        "vector_index": "pgvector_hnsw_cosine" if index_enabled else None,
        "indexed_embeddings": embedding_count,
        "compatible_embeddings": compatible_count,
        "index_compatible": index_enabled and (chunk_count == 0 or compatible_count == chunk_count),
        "reindex_required": chunk_count > compatible_count,
    }
