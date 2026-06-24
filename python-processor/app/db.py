from __future__ import annotations

import logging
import uuid
from typing import Any

import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.metrics import DB_CONNECTION_ERRORS, DB_CONNECTION_SECONDS
from app.runtime import DATABASE_URL

logger = logging.getLogger(__name__)

def get_db():
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="DATABASE_URL nincs beallitva.")
    with DB_CONNECTION_SECONDS.time():
        try:
            return psycopg.connect(DATABASE_URL, row_factory=dict_row)
        except Exception as exc:
            DB_CONNECTION_ERRORS.inc()
            raise HTTPException(status_code=503, detail=f"Adatbazis kapcsolat sikertelen: {exc}") from exc

def validated_optional_uuid(value: str | None, field_name: str) -> str | None:
    if value in (None, ""):
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail=f"invalid_{field_name}") from exc

def write_audit_event(
    event_type: str, *, entity_type: str | None = None, entity_id: str | None = None,
    success: bool = True, actor: str = "system", details: dict[str, Any] | None = None,
) -> None:
    """Best-effort operational audit. Audit failure never masks the main action."""
    if not DATABASE_URL:
        return
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO audit_events
                      (actor, event_type, entity_type, entity_id, success, details)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (actor, event_type, entity_type, entity_id, success, Jsonb(details or {})),
                )
            conn.commit()
    except Exception as exc:
        logger.exception("audit_event_write_failed", extra={"structured": {"event_type": event_type, "entity_type": entity_type}})

# Temporary compatibility aliases while domain routers are migrated.
_validated_optional_uuid = validated_optional_uuid
_write_audit_event = write_audit_event
