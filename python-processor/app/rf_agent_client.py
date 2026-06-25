from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RfAgentSettings:
    """Connection settings for the native C++ RF agent.

    The backend treats the RF agent as optional. Core mode remains healthy when
    the agent is disabled or temporarily unreachable.
    """

    enabled: bool
    base_url: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> "RfAgentSettings":
        enabled = os.getenv("RF_AGENT_INTEGRATION_ENABLED", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        try:
            timeout = max(0.5, min(30.0, float(os.getenv("RF_AGENT_TIMEOUT_SECONDS", "3"))))
        except ValueError:
            timeout = 3.0
        return cls(
            enabled=enabled,
            base_url=os.getenv("RF_AGENT_URL", "http://rf-agent:8765").rstrip("/"),
            timeout_seconds=timeout,
        )


class RfAgentUnavailable(RuntimeError):
    pass


def request_rf_agent(
    settings: RfAgentSettings,
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not settings.enabled:
        raise RfAgentUnavailable("rf_agent_integration_disabled")
    if not path.startswith("/"):
        raise ValueError("RF agent path must start with '/'")

    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        settings.base_url + path,
        data=payload,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.timeout_seconds) as response:
            parsed = json.load(response)
            if not isinstance(parsed, dict):
                raise RfAgentUnavailable("rf_agent_invalid_response")
            return parsed
    except urllib.error.HTTPError as exc:
        try:
            details = json.load(exc)
        except (json.JSONDecodeError, OSError):
            details = {"error": {"code": "RF_AGENT_HTTP_ERROR", "message": str(exc)}}
        message = json.dumps(details, ensure_ascii=False)
        raise RfAgentUnavailable(f"rf_agent_http_{exc.code}: {message}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RfAgentUnavailable(f"rf_agent_unavailable: {exc}") from exc


def rf_agent_status(settings: RfAgentSettings) -> dict[str, Any]:
    if not settings.enabled:
        return {
            "implemented": True,
            "enabled": False,
            "available": False,
            "status": "disabled",
            "url": settings.base_url,
        }
    try:
        value = request_rf_agent(settings, "/status")
    except RfAgentUnavailable as exc:
        return {
            "implemented": True,
            "enabled": True,
            "available": False,
            "status": "unreachable",
            "url": settings.base_url,
            "error": str(exc),
        }
    return {
        "implemented": True,
        "enabled": True,
        "available": True,
        "status": "ready",
        "url": settings.base_url,
        "agent": value,
    }
