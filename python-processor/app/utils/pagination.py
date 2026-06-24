from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from uuid import UUID


def encode_time_uuid_cursor(timestamp: datetime, identifier: UUID | str) -> str:
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    payload = {
        "t": timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "i": str(identifier),
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_time_uuid_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode((cursor + padding).encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        timestamp_text = str(payload["t"])
        if timestamp_text.endswith("Z"):
            timestamp_text = timestamp_text[:-1] + "+00:00"
        timestamp = datetime.fromisoformat(timestamp_text)
        if timestamp.tzinfo is None:
            raise ValueError("cursor timestamp must include timezone")
        identifier = UUID(str(payload["i"]))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("invalid_pagination_cursor") from exc
    return timestamp.astimezone(timezone.utc), identifier
