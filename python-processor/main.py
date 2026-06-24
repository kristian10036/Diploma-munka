"""Compatibility entrypoint for ``uvicorn main:app``."""

from app.application import app

__all__ = ["app"]
