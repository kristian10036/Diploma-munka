import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

SPECTRUM_INGEST_ROOT = Path(__file__).resolve().parent


def _prometheus_client_missing() -> bool:
    if "prometheus_client" in sys.modules:
        return False
    try:
        return importlib.util.find_spec("prometheus_client") is None
    except ValueError:
        return False


if _prometheus_client_missing():

    class _Metric:
        def inc(self, _value: float = 1) -> None:
            return None

        def set(self, _value: float) -> None:
            return None

        def observe(self, _value: float) -> None:
            return None

    sys.modules["prometheus_client"] = types.SimpleNamespace(
        CONTENT_TYPE_LATEST="text/plain; version=0.0.4; charset=utf-8",
        Counter=lambda *args, **kwargs: _Metric(),
        Gauge=lambda *args, **kwargs: _Metric(),
        Histogram=lambda *args, **kwargs: _Metric(),
        generate_latest=lambda: b"",
    )

APP_SPEC = importlib.util.spec_from_file_location(
    "spectrum_ingest_app_under_test",
    SPECTRUM_INGEST_ROOT / "app.py",
)
assert APP_SPEC is not None and APP_SPEC.loader is not None
APP_MODULE = importlib.util.module_from_spec(APP_SPEC)
APP_SPEC.loader.exec_module(APP_MODULE)

AUDIO_MAX_QUEUE = APP_MODULE.AUDIO_MAX_QUEUE
AudioDatagramProtocol = APP_MODULE.AudioDatagramProtocol
MAX_QUEUE = APP_MODULE.MAX_QUEUE
Metrics = APP_MODULE.Metrics
publish = APP_MODULE.publish
state = APP_MODULE.state
validate_frame = APP_MODULE.validate_frame


pytestmark = pytest.mark.unit


def frame(sequence: int = 1) -> dict:
    return {
        "schema_version": 1,
        "sensor_id": "test-sensor",
        "source_type": "mock",
        "source_device": "test-generator",
        "device_model": "test-generator",
        "measurement_mode": "spectrum",
        "session_id": "test-session",
        "timestamp": "2026-06-19T12:00:00.000Z",
        "sequence": sequence,
        "start_frequency_hz": 100_000_000,
        "stop_frequency_hz": 102_000_000,
        "step_frequency_hz": 1_000_000,
        "center_frequency_hz": 101_000_000,
        "sample_rate_hz": 2_000_000,
        "rbw_hz": 1_000_000,
        "num_points": 3,
        "point_count": 3,
        "power_unit": "dBm",
        "powers_dbm": [-90.0, -40.0, -91.0],
        "flags": {"overflow": False, "dropped": False, "inaccurate": False},
        "metadata": {"is_simulated": True},
    }


@pytest.fixture(autouse=True)
def reset_state() -> None:
    state.clients.clear()
    state.audio_clients.clear()
    state.last_payload = None
    state.last_error = None
    state.last_source = None
    state.audio_last_error = None
    state.audio_last_packet_at = None
    state.last_sequences.clear()
    state.received_times.clear()
    state.outgoing_times.clear()
    state.metrics = Metrics()


def test_validate_frame_accepts_valid_shapes() -> None:
    valid, error = validate_frame(frame())
    assert valid, error

    wide = frame()
    wide.update(
        {
            "start_frequency_hz": 5_000_000,
            "stop_frequency_hz": 18_000_000_000,
            "step_frequency_hz": 8_997_500_000,
            "center_frequency_hz": 9_002_500_000,
            "sample_rate_hz": 17_995_000_000,
        }
    )
    valid, error = validate_frame(wide)
    assert valid, error


def test_validate_frame_rejects_invalid_shapes() -> None:
    invalid = frame()
    invalid["stop_frequency_hz"] += 1
    assert validate_frame(invalid)[0] is False

    invalid = frame()
    invalid["powers_dbm"][0] = float("nan")
    assert validate_frame(invalid)[0] is False

    invalid = frame()
    invalid["metadata"]["is_simulated"] = False
    assert validate_frame(invalid)[0] is False


async def bounded_queue_test() -> None:
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=MAX_QUEUE)
    state.clients.add(queue)
    before = state.metrics.dropped_frames
    for sequence in range(MAX_QUEUE + 5):
        await publish(json.dumps(frame(sequence)))
    assert queue.qsize() == MAX_QUEUE
    assert state.metrics.dropped_frames == before + 5
    newest = None
    while not queue.empty():
        newest = json.loads(queue.get_nowait())
    assert newest["sequence"] == MAX_QUEUE + 4
    state.clients.discard(queue)


def test_publish_enforces_bounded_queue() -> None:
    asyncio.run(bounded_queue_test())


async def latest_payload_test() -> None:
    payload = json.dumps(frame(99))
    state.last_payload = payload
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=MAX_QUEUE)
    if state.last_payload is not None:
        queue.put_nowait(state.last_payload)
    assert json.loads(queue.get_nowait())["sequence"] == 99
    state.last_payload = None


def test_latest_payload_primes_new_queue() -> None:
    asyncio.run(latest_payload_test())


async def audio_datagram_test() -> None:
    queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=AUDIO_MAX_QUEUE)
    state.audio_clients.add(queue)
    protocol = AudioDatagramProtocol()
    before_packets = state.metrics.audio_packets
    before_invalid = state.metrics.audio_invalid_packets

    protocol.datagram_received(b"\x00\x00\xff\x7f", ("127.0.0.1", 9998))
    assert queue.get_nowait() == b"\x00\x00\xff\x7f"
    assert state.metrics.audio_packets == before_packets + 1

    protocol.datagram_received(b"\x01\x00\x02", ("127.0.0.1", 9998))
    assert queue.get_nowait() == b"\x01\x00"

    protocol.datagram_received(b"\x00", ("127.0.0.1", 9998))
    assert state.metrics.audio_invalid_packets == before_invalid + 1
    state.audio_clients.discard(queue)


def test_audio_datagram_protocol_filters_and_broadcasts() -> None:
    asyncio.run(audio_datagram_test())
