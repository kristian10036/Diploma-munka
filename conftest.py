import os
import sys
from collections.abc import Iterator
from importlib.machinery import ModuleSpec
from importlib.util import find_spec
from pathlib import Path
import types

import pytest


ROOT = Path(__file__).resolve().parent
PYTHON_PROCESSOR_ROOT = ROOT / "python-processor"
PATH_MARKERS = (
    ("python-processor/tests/", ("backend", "offline")),
    ("spectrum-ingest/", ("backend", "offline")),
    ("tests/frontend/", ("frontend", "offline")),
    ("tests/api/", ("api", "integration")),
    ("tests/websocket/", ("websocket", "integration")),
    ("tests/integration/", ("integration",)),
)

if str(PYTHON_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_PROCESSOR_ROOT))

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


if find_spec("prometheus_client") is None:
    class _Metric:
        def labels(self, *args, **kwargs):
            return self

        def inc(self, _value: float = 1) -> None:
            return None

        def set(self, _value: float) -> None:
            return None

        def observe(self, _value: float) -> None:
            return None

    prometheus_client = types.ModuleType("prometheus_client")
    prometheus_client.__spec__ = ModuleSpec("prometheus_client", loader=None)
    prometheus_client.CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    prometheus_client.Counter = lambda *args, **kwargs: _Metric()
    prometheus_client.Gauge = lambda *args, **kwargs: _Metric()
    prometheus_client.Histogram = lambda *args, **kwargs: _Metric()
    prometheus_client.REGISTRY = object()
    prometheus_client.generate_latest = lambda: b""
    sys.modules["prometheus_client"] = prometheus_client


@pytest.fixture(scope="session", autouse=True)
def stable_test_environment() -> Iterator[None]:
    previous = {}
    defaults = {
        "APP_MODE": "demo",
        "LOG_LEVEL": "ERROR",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }
    for key, value in defaults.items():
        previous[key] = os.environ.get(key)
        os.environ.setdefault(key, value)
    yield
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def python_processor_root() -> Path:
    return PYTHON_PROCESSOR_ROOT


@pytest.fixture(scope="session")
def backend_url() -> str:
    return os.environ.get("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


@pytest.fixture(scope="session")
def rf_agent_ws_url() -> str:
    return os.environ.get("RF_AGENT_WS_URL", "ws://127.0.0.1:8765/ws/spectrum")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        path = Path(str(item.fspath)).resolve().relative_to(ROOT).as_posix()
        for prefix, markers in PATH_MARKERS:
            if path.startswith(prefix):
                for marker in markers:
                    item.add_marker(marker)
                break
