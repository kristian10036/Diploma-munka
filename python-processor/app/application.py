from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.logging_config import bind_request_context, configure_logging, reset_request_context
from app.security import SETTINGS, authorize_request

configure_logging()
logger = logging.getLogger(__name__)


def _error_response(
    *, request: Request, status_code: int, code: str, message: str, details=None, headers=None
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id")
    payload = {
        "detail": message,
        "code": code,
        "message": message,
        "details": details,
        "request_id": request_id,
    }
    return JSONResponse(status_code=status_code, content=payload, headers=headers or {})


def create_application() -> FastAPI:
    # Validate production-critical configuration before importing heavy optional
    # subsystems (NumPy/ML, collectors, RF clients). A bad production config
    # therefore fails immediately and deterministically.
    SETTINGS.validate()
    from app.db import write_audit_event
    from app.metrics import install_metrics
    from app.routers import (
        anomalies_alerts,
        data_retention,
        device_baseline,
        health_collectors,
        legacy_references,
        markers_known,
        observations,
        recordings,
        reference_sets,
        rf_agent,
        sessions_imports,
        spectrum_actions,
        system_rag,
        versioned_references,
    )
    from app.routers.monitoring import router as monitoring_router
    from app.streaming import router as streaming_router
    from app.streaming import shutdown_event, startup_event

    app = FastAPI(title="DM RF/TSCM monitoring platform", version="2.0.0")

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "request_failed"
        details = None if isinstance(exc.detail, str) else exc.detail
        return _error_response(
            request=request,
            status_code=exc.status_code,
            code=message,
            message=message,
            details=details,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return _error_response(
            request=request,
            status_code=422,
            code="request_validation_error",
            message="request_validation_error",
            details=exc.errors(),
        )

    @app.middleware("http")
    async def request_context_and_security(request: Request, call_next):
        request_id = request.headers.get("x-request-id", "").strip()[:128] or str(uuid.uuid4())
        request.state.request_id = request_id
        tokens = bind_request_context(
            request_id=request_id,
            session_id=request.headers.get("x-session-id"),
            recording_id=request.headers.get("x-recording-id"),
            source_id=request.headers.get("x-source-id"),
        )
        started = time.perf_counter()
        status_code = 500
        auth = {"actor": "unknown", "role": "unknown"}
        try:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    declared_length = int(content_length)
                except ValueError:
                    status_code = 400
                    return _error_response(
                        request=request,
                        status_code=400,
                        code="invalid_content_length",
                        message="invalid_content_length",
                    )
                if declared_length < 0:
                    status_code = 400
                    return _error_response(
                        request=request,
                        status_code=400,
                        code="invalid_content_length",
                        message="invalid_content_length",
                    )
                if declared_length > SETTINGS.max_request_bytes:
                    status_code = 413
                    return _error_response(
                        request=request,
                        status_code=413,
                        code="request_body_too_large",
                        message="request_body_too_large",
                    )
            try:
                auth = authorize_request(request)
            except HTTPException as exc:
                status_code = exc.status_code
                return _error_response(
                    request=request,
                    status_code=exc.status_code,
                    code=str(exc.detail),
                    message=str(exc.detail),
                    headers=exc.headers,
                )
            request.state.auth = auth
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            response.headers["Cache-Control"] = (
                "no-store"
                if request.url.path.startswith("/api/")
                else response.headers.get("Cache-Control", "no-cache")
            )
            return response
        except Exception:
            logger.exception(
                "request_failed",
                extra={"structured": {"method": request.method, "path": request.url.path}},
            )
            raise
        finally:
            duration = time.perf_counter() - started
            logger.info(
                "request_complete",
                extra={
                    "structured": {
                        "method": request.method,
                        "path": request.url.path,
                        "status": status_code,
                        "duration_seconds": round(duration, 6),
                        "role": auth.get("role"),
                    }
                },
            )
            if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith(
                "/api/"
            ):
                write_audit_event(
                    "api.write",
                    entity_type="http_request",
                    actor=auth.get("actor", "unknown"),
                    success=200 <= status_code < 400,
                    details={
                        "method": request.method,
                        "path": request.url.path,
                        "status": status_code,
                        "request_id": request_id,
                    },
                )
            reset_request_context(tokens)

    install_metrics(app)
    for router in (
        health_collectors.router,
        sessions_imports.router,
        observations.router,
        anomalies_alerts.router,
        legacy_references.router,
        versioned_references.router,
        reference_sets.router,
        spectrum_actions.router,
        markers_known.router,
        recordings.router,
        rf_agent.router,
        system_rag.router,
        monitoring_router,
        streaming_router,
        data_retention.router,
        device_baseline.router,
    ):
        app.include_router(router)
    if hasattr(app, "add_event_handler"):
        app.add_event_handler("startup", startup_event)
        app.add_event_handler("shutdown", shutdown_event)
    else:
        app.router.on_event("startup")(startup_event)
        app.router.on_event("shutdown")(shutdown_event)
    static_path = Path(__file__).resolve().parent.parent / "static"
    app.mount("/", StaticFiles(directory=static_path, html=True), name="static")
    return app


app = create_application()
