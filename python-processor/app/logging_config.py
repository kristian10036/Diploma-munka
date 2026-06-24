from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
session_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("session_id", default="-")
recording_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("recording_id", default="-")
source_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("source_id", default="-")

_SECRET_MARKERS = ("password", "secret", "token", "authorization", "api_key", "apikey")


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "***" if any(marker in str(key).lower() for marker in _SECRET_MARKERS) else _safe(item)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    text = str(value)
    return text if len(text) <= 2000 else text[:2000] + "…"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "service": os.getenv("SERVICE_NAME", "tscm-backend"),
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "session_id": session_id_var.get(),
            "recording_id": recording_id_var.get(),
            "source_id": source_id_var.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        extra = getattr(record, "structured", None)
        if extra is not None:
            payload["context"] = _safe(extra)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        return f"{base} request_id={request_id_var.get()} session_id={session_id_var.get()} recording_id={recording_id_var.get()} source_id={source_id_var.get()}"


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    log_format = os.getenv("LOG_FORMAT", "json").lower()
    handler = logging.StreamHandler(sys.stdout)
    if log_format == "text":
        handler.setFormatter(TextFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    else:
        handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True


def bind_request_context(*, request_id: str, session_id: str | None = None,
                         recording_id: str | None = None, source_id: str | None = None) -> list[tuple[contextvars.ContextVar[str], contextvars.Token[str]]]:
    values = ((request_id_var, request_id), (session_id_var, session_id or "-"),
              (recording_id_var, recording_id or "-"), (source_id_var, source_id or "-"))
    return [(variable, variable.set(value)) for variable, value in values]


def reset_request_context(tokens: list[tuple[contextvars.ContextVar[str], contextvars.Token[str]]]) -> None:
    for variable, token in reversed(tokens):
        variable.reset(token)
