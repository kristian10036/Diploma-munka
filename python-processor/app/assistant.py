from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def model_is_installed(model: str, installed: set[str]) -> bool:
    return model in installed or (":" not in model and f"{model}:latest" in installed)


@dataclass(frozen=True)
class AssistantSettings:
    enabled: bool
    ollama_url: str
    model: str
    timeout_seconds: float
    max_context_records: int
    max_prompt_chars: int = 12_000
    max_source_records: int = 20
    num_predict: int = 768

    @classmethod
    def from_env(cls) -> "AssistantSettings":
        enabled = os.getenv("AI_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
        try:
            timeout = max(1.0, min(600.0, float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300"))))
        except ValueError:
            timeout = 20.0
        try:
            limit = max(1, min(50, int(os.getenv("ASSISTANT_MAX_CONTEXT_RECORDS", "10"))))
        except ValueError:
            limit = 10
        try:
            max_prompt_chars = max(
                2_000, min(60_000, int(os.getenv("ASSISTANT_MAX_PROMPT_CHARS", "12000")))
            )
        except ValueError:
            max_prompt_chars = 12_000
        try:
            max_source_records = max(
                1, min(100, int(os.getenv("ASSISTANT_MAX_SOURCE_RECORDS", "20")))
            )
        except ValueError:
            max_source_records = 20
        try:
            num_predict = max(64, min(2048, int(os.getenv("ASSISTANT_NUM_PREDICT", "768"))))
        except ValueError:
            num_predict = 768
        return cls(
            enabled=enabled,
            ollama_url=os.getenv("OLLAMA_URL", "http://ollama:11434").rstrip("/"),
            model=os.getenv("OLLAMA_MODEL", "").strip(),
            timeout_seconds=timeout,
            max_context_records=limit,
            max_prompt_chars=max_prompt_chars,
            max_source_records=max_source_records,
            num_predict=num_predict,
        )

    def status(self) -> dict[str, Any]:
        """Return generation-model status only.

        RAG is a separate retrieval subsystem and is aggregated by the API
        endpoint from the live database/vector-index state. Keeping it out of
        this value prevents the old hard-coded ``not_implemented`` status from
        contradicting the implemented pgvector pipeline.
        """
        available = self.enabled and bool(self.model)
        return {
            "implemented": True,
            "enabled": self.enabled,
            "available": available,
            "status": "configured"
            if available
            else ("model_not_configured" if self.enabled else "disabled"),
            "mode": "context_grounded_assistant",
            "model": self.model or None,
        }

    def live_status(self) -> dict[str, Any]:
        """Return configuration status enriched with a bounded Ollama probe."""
        configured = self.status()
        if not configured["available"]:
            return configured
        try:
            with urllib.request.urlopen(
                urllib.request.Request(
                    self.ollama_url + "/api/version", headers={"Accept": "application/json"}
                ),
                timeout=min(self.timeout_seconds, 3.0),
            ) as response:
                version_payload = json.load(response)
            with urllib.request.urlopen(
                urllib.request.Request(
                    self.ollama_url + "/api/tags", headers={"Accept": "application/json"}
                ),
                timeout=min(self.timeout_seconds, 3.0),
            ) as response:
                payload = json.load(response)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            return {
                **configured,
                "available": False,
                "status": "ollama_unavailable",
                "error": str(exc),
            }
        if not isinstance(version_payload, dict) or not isinstance(
            version_payload.get("version"), str
        ):
            return {**configured, "available": False, "status": "ollama_invalid_response"}
        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
            return {
                **configured,
                "available": False,
                "status": "ollama_invalid_response",
                "ollama_version": version_payload["version"],
            }
        installed = {
            str(item.get("name") or item.get("model") or "")
            for item in payload.get("models", [])
            if isinstance(item, dict)
        }
        if not model_is_installed(self.model, installed):
            return {
                **configured,
                "available": False,
                "status": "model_not_installed",
                "installed_models": sorted(name for name in installed if name),
                "ollama_version": version_payload["version"],
            }
        return {
            **configured,
            "status": "ready",
            "ollama_version": version_payload["version"],
            "installed_models": sorted(name for name in installed if name),
        }


KEYWORDS = {
    "sessions": (
        "session",
        "mérés",
        "meres",
        "helyszín",
        "helyszin",
        "operátor",
        "operator",
    ),
    "wifi": (
        "wifi",
        "wi-fi",
        "ssid",
        "bssid",
        "mac",
        "mac cím",
        "mac-cím",
        "mac cim",
        "csatorna",
        "channel",
    ),
    "bluetooth": (
        "bluetooth",
        "ble",
        "mac",
        "mac cím",
        "mac-cím",
        "mac cim",
        "service uuid",
    ),
    "peaks": (
        "peak",
        "csúcs",
        "csucs",
        "frekvencia",
        "frequency",
        "spektrum",
        "spectrum",
    ),
    "anomalies": (
        "anomália",
        "anomalia",
        "anomaly",
        "riaszt",
        "alert",
    ),
}


def select_context_kinds(question: str) -> tuple[str, ...]:
    normalized = question.casefold()
    selected = [
        kind for kind, words in KEYWORDS.items() if any(word in normalized for word in words)
    ]
    if any(
        word in normalized
        for word in (
            "összefoglal",
            "osszefoglal",
            "foglald össze",
            "foglald ossze",
            "minden",
            "overview",
        )
    ):
        return tuple(KEYWORDS)
    return tuple(selected or ("sessions", "peaks", "anomalies"))


def is_mac_inventory_question(question: str) -> bool:
    """Identify requests that require a complete MAC inventory, not samples."""
    normalized = question.casefold()
    asks_about_mac = "mac" in normalized or "bssid" in normalized
    asks_for_complete_list = any(
        term in normalized
        for term in (
            "minden",
            "összes",
            "osszes",
            "valamennyi",
            "teljes lista",
            "listáz",
            "listaz",
            "sorold",
            "mutasd",
        )
    )
    return asks_about_mac and asks_for_complete_list


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


QUERIES = {
    "sessions": """
        SELECT id::text, location_name, operator_name, started_at, ended_at, status, mode, title
        FROM measurement_sessions ORDER BY started_at DESC LIMIT %s
    """,
    "wifi": """
        SELECT observation.id::text, observation.time, observation.bssid,
               COALESCE(observation.ssid, device.ssid) AS ssid,
               observation.channel, observation.frequency_hz, observation.rssi_dbm,
               location.name AS location_name
        FROM wifi_observations observation
        LEFT JOIN wifi_devices device ON device.bssid = observation.bssid
        LEFT JOIN locations location ON location.id = observation.location_id
        ORDER BY observation.time DESC LIMIT %s
    """,
    "bluetooth": """
        SELECT observation.id::text, observation.time, observation.mac_address,
               COALESCE(observation.device_name, device.device_name) AS device_name,
               observation.service_uuid, observation.rssi_dbm,
               location.name AS location_name
        FROM bluetooth_observations observation
        LEFT JOIN bluetooth_devices device ON device.mac_address = observation.mac_address
        LEFT JOIN locations location ON location.id = observation.location_id
        ORDER BY observation.time DESC LIMIT %s
    """,
    "peaks": """
        SELECT peak.id::text, peak.time, peak.session_id::text, peak.peak_type,
               peak.frequency_hz, peak.power_dbm, location.name AS location_name
        FROM spectrum_peaks peak
        LEFT JOIN locations location ON location.id = peak.location_id
        ORDER BY peak.time DESC LIMIT %s
    """,
    "anomalies": """
        SELECT anomaly.id::text, anomaly.time, anomaly.session_id::text,
               anomaly.anomaly_type, anomaly.severity, anomaly.status,
               anomaly.frequency_hz, anomaly.measured_power_dbm, anomaly.description,
               location.name AS location_name
        FROM anomalies anomaly
        LEFT JOIN locations location ON location.id = anomaly.location_id
        ORDER BY anomaly.time DESC LIMIT %s
    """,
}


def collect_sql_context(
    connection: Any, question: str, limit: int
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, str]]]:
    context: dict[str, list[dict[str, Any]]] = {}
    sources: list[dict[str, str]] = []
    with connection.cursor() as cursor:
        for kind in select_context_kinds(question):
            cursor.execute(QUERIES[kind], (limit,))
            rows = [json_safe(dict(row)) for row in cursor.fetchall()]
            context[kind] = rows
            for row in rows:
                if row.get("id"):
                    source = {"record_type": kind, "record_id": str(row["id"])}
                    if row.get("time") or row.get("started_at"):
                        source["timestamp"] = str(row.get("time") or row.get("started_at"))
                    sources.append(source)
    return context, sources


_MAX_FIELD_CHARS = 280


def _trim_field(value: Any) -> Any:
    """Cap an individual record field so one oversized free-text value (e.g.
    an anomaly description) can't crowd out other records in the budget."""
    if isinstance(value, str) and len(value) > _MAX_FIELD_CHARS:
        return value[: _MAX_FIELD_CHARS - 3] + "..."
    return value


def _trim_record(record: Any) -> Any:
    if isinstance(record, dict):
        return {key: _trim_field(value) for key, value in record.items()}
    return record


def _pack_context_by_budget(context: dict[str, Any], budget_chars: int) -> dict[str, Any]:
    """Fill per-kind sample records up to a character budget instead of a
    fixed count. Records arrive ordered most-recent-first from SQL, and kinds
    are ordered by question-relevance (see select_context_kinds), so filling
    round-robin in that order and stopping a kind once it would blow the
    budget drops the least-relevant (oldest/least-matched) rows first -
    never a mid-record or mid-string cut.
    """
    bounded: dict[str, Any] = {}
    queues: dict[str, list[Any]] = {}
    for kind, records in context.items():
        if isinstance(records, list):
            bounded[kind] = {"supplied_count": len(records), "records": []}
            queues[kind] = [_trim_record(record) for record in records]
        else:
            bounded[kind] = records

    def serialized_size() -> int:
        return len(json.dumps(bounded, ensure_ascii=False, separators=(",", ":")))

    exhausted: set[str] = {kind for kind, queue in queues.items() if not queue}
    while len(exhausted) < len(queues):
        progressed = False
        for kind, queue in queues.items():
            if kind in exhausted:
                continue
            bounded[kind]["records"].append(queue[0])
            if serialized_size() > budget_chars:
                bounded[kind]["records"].pop()
                exhausted.add(kind)
                continue
            queue.pop(0)
            progressed = True
            if not queue:
                exhausted.add(kind)
        if not progressed:
            break
    return bounded


def build_grounded_prompt(
    question: str,
    context: dict[str, Any],
    sources: list[dict[str, str]],
    max_prompt_chars: int = 12_000,
    max_source_records: int = 20,
) -> str:
    capped_sources = sources[:max_source_records]
    sources_reserve = len(
        json.dumps(
            {"source_records": capped_sources}, ensure_ascii=False, separators=(",", ":")
        )
    )
    context_budget = max(200, max_prompt_chars - sources_reserve)
    bounded_context = _pack_context_by_budget(context, context_budget)
    payload = json.dumps(
        {"context": bounded_context, "source_records": capped_sources},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    while len(payload) > max_prompt_chars and capped_sources:
        capped_sources = capped_sources[:-1]
        payload = json.dumps(
            {"context": bounded_context, "source_records": capped_sources},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    normalized = question.casefold()
    hungarian_markers = (
        "á",
        "é",
        "í",
        "ó",
        "ö",
        "ő",
        "ú",
        "ü",
        "ű",
        "milyen",
        "mennyi",
        "foglald",
        "kérdés",
    )
    language = (
        "Hungarian (hu)"
        if any(marker in normalized for marker in hungarian_markers)
        else "the language used by the question"
    )
    return (
        "You are a measurement-data assistant. Use only the supplied context. "
        "Never invent measurements, identities, causes, or conclusions. "
        "If evidence is insufficient, say so. "
        "Return plain, natural human-readable prose, never JSON. Do not repeat the question. "
        "Use clear bullet lists where useful. "
        "Cite relevant records as [record_type:record_id].\n\n"
        f"Structured context: {payload}\n\n"
        f"Question: {question}\n"
        f"Required answer language: {language}. This language requirement is mandatory. "
        "Answer the question directly; do not interpret language instructions as names "
        "or measurement entities."
    )


def normalize_ollama_answer(answer: str) -> str:
    """Return displayable prose even if a model wraps it in a JSON object."""
    cleaned = answer.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1]).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        return cleaned
    if isinstance(value, dict):
        for key in ("answer", "response", "message", "content"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return cleaned


def call_ollama(settings: AssistantSettings, prompt: str) -> str:
    if not settings.enabled or not settings.model:
        raise RuntimeError("ai_component_not_available")
    request = urllib.request.Request(
        settings.ollama_url + "/api/generate",
        data=json.dumps(
            {
                "model": settings.model,
                "prompt": prompt,
                "stream": False,
                # Qwen 3 enables reasoning by default. With a bounded output budget
                # it can spend every token on the separate `thinking` field and
                # return an empty `response`, which is unusable by this endpoint.
                "think": False,
                "keep_alive": "10m",
                "options": {
                    "num_ctx": 4096,
                    "num_predict": settings.num_predict,
                    "temperature": 0.1,
                },
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.timeout_seconds) as response:
            value = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"ollama_unavailable: {exc}") from exc
    answer = value.get("response")
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("ollama_invalid_response")
    return normalize_ollama_answer(answer)
