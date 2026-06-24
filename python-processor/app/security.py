from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_PUBLIC_WRITE_PATHS = {"/api/health", "/api/health/live", "/api/health/ready", "/api/health/status"}


def _boolean(name: str, default: bool = False) -> bool:
    return os.getenv(name, "true" if default else "false").strip().lower() in {"1", "true", "yes", "on"}


def _default_synthetic_fallback(app_mode: str) -> bool:
    return app_mode != "production"


@dataclass(frozen=True, slots=True)
class SecuritySettings:
    app_mode: str
    allow_synthetic_fallback: bool
    auth_mode: str
    anonymous_read: bool
    operator_token_sha256: str
    admin_token_sha256: str
    max_request_bytes: int

    @classmethod
    def from_env(cls) -> "SecuritySettings":
        raw_max_request_bytes = os.getenv("MAX_REQUEST_BYTES", str(200 * 1024 * 1024)).strip()
        try:
            max_request_bytes = int(raw_max_request_bytes)
        except ValueError as exc:
            raise RuntimeError(
                "Invalid production configuration: MAX_REQUEST_BYTES must be an integer"
            ) from exc
        app_mode = os.getenv("APP_PROFILE", os.getenv("APP_MODE", "demo")).strip().lower()
        allow_synthetic_fallback_env = os.getenv("ALLOW_SYNTHETIC_FALLBACK", "").strip().lower()
        if allow_synthetic_fallback_env:
            allow_synthetic_fallback = allow_synthetic_fallback_env in {"1", "true", "yes", "on"}
        else:
            allow_synthetic_fallback = _default_synthetic_fallback(app_mode)
        return cls(
            app_mode=app_mode,
            allow_synthetic_fallback=allow_synthetic_fallback,
            auth_mode=os.getenv("AUTH_MODE", "disabled").strip().lower(),
            anonymous_read=_boolean("AUTH_ANONYMOUS_READ", True),
            operator_token_sha256=os.getenv("AUTH_OPERATOR_TOKEN_SHA256", "").strip().lower(),
            admin_token_sha256=os.getenv("AUTH_ADMIN_TOKEN_SHA256", "").strip().lower(),
            max_request_bytes=max(1024, max_request_bytes),
        )

    def validate(self) -> None:
        errors: list[str] = []
        if self.app_mode not in {"demo", "production"}:
            errors.append("APP_MODE must be demo or production")
        if self.app_mode == "production" and self.allow_synthetic_fallback:
            errors.append("ALLOW_SYNTHETIC_FALLBACK must be false in production")
        if self.auth_mode not in {"disabled", "api_token"}:
            errors.append("AUTH_MODE must be disabled or api_token")
        for name, value in (("AUTH_OPERATOR_TOKEN_SHA256", self.operator_token_sha256),
                            ("AUTH_ADMIN_TOKEN_SHA256", self.admin_token_sha256)):
            if value and (len(value) != 64 or any(char not in "0123456789abcdef" for char in value)):
                errors.append(f"{name} must be a lowercase SHA-256 hex digest")
        if self.app_mode == "production":
            if not os.getenv("DATABASE_URL", "").strip():
                errors.append("DATABASE_URL is required in production")
            if self.auth_mode != "api_token":
                errors.append("AUTH_MODE=api_token is required in production")
            if not self.operator_token_sha256 and not self.admin_token_sha256:
                errors.append("At least one operator/admin token hash is required in production")
            unsafe = {"change_me_dev_only", "change_this_password", "postgres", "password"}
            password = os.getenv("POSTGRES_PASSWORD", "").strip().lower()
            if password in unsafe:
                errors.append("Default/unsafe POSTGRES_PASSWORD is forbidden in production")
        if errors:
            raise RuntimeError("Invalid production configuration: " + "; ".join(errors))


SETTINGS = SecuritySettings.from_env()


def _token_role(token: str) -> str | None:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if SETTINGS.admin_token_sha256 and hmac.compare_digest(digest, SETTINGS.admin_token_sha256):
        return "admin"
    if SETTINGS.operator_token_sha256 and hmac.compare_digest(digest, SETTINGS.operator_token_sha256):
        return "operator"
    return None


def authorize_request(request: Request) -> dict[str, Any]:
    if SETTINGS.auth_mode == "disabled":
        return {"role": "demo", "actor": "anonymous-demo"}
    requires_auth = request.method.upper() in _WRITE_METHODS or not SETTINGS.anonymous_read
    if request.url.path in _PUBLIC_WRITE_PATHS:
        requires_auth = False
    if not requires_auth:
        return {"role": "viewer", "actor": "anonymous-viewer"}
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="bearer_token_required", headers={"WWW-Authenticate": "Bearer"})
    role = _token_role(token)
    if role not in {"operator", "admin"}:
        raise HTTPException(status_code=403, detail="operator_or_admin_role_required")
    return {"role": role, "actor": f"{role}-token"}
