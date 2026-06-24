"""Guards against unintentional public API contract drift.

Regenerate the snapshot after an intentional API change with:
    UPDATE_OPENAPI_SNAPSHOT=1 python -m pytest tests/test_openapi_snapshot.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.application import app

SNAPSHOT_PATH = Path(__file__).resolve().parent / "fixtures" / "openapi_snapshot.json"


def _current_schema() -> dict:
    app.openapi_schema = None
    return app.openapi()


def test_openapi_schema_matches_committed_snapshot():
    current = _current_schema()
    if os.environ.get("UPDATE_OPENAPI_SNAPSHOT") == "1":
        SNAPSHOT_PATH.write_text(
            json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return
    assert SNAPSHOT_PATH.exists(), (
        "missing tests/fixtures/openapi_snapshot.json; generate it with UPDATE_OPENAPI_SNAPSHOT=1"
    )
    committed = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert current == committed, (
        "OpenAPI schema changed. If this is intentional, regenerate the snapshot with "
        "UPDATE_OPENAPI_SNAPSHOT=1 python -m pytest tests/test_openapi_snapshot.py"
    )
