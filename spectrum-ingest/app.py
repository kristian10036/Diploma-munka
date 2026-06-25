import asyncio
import contextlib
import json
import logging
import math
import os
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import websockets
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

RF_AGENT_WS_URL = os.getenv("RF_AGENT_WS_URL", "ws://rf-agent:8765/ws/spectrum")
MAX_QUEUE = max(1, min(256, int(os.getenv("SPECTRUM_INGEST_MAX_QUEUE", "32"))))
RECONNECT_SECONDS = max(0.1, float(os.getenv("SPECTRUM_INGEST_RECONNECT_SECONDS", "2")))
CLIENT_MAX_FPS = max(0.1, float(os.getenv("SPECTRUM_CLIENT_MAX_FPS", "5")))
MAX_FRAME_BYTES = max(1024, int(os.getenv("SPECTRUM_INGEST_MAX_FRAME_BYTES", str(4 * 1024 * 1024))))
MAX_POINTS = max(1, int(os.getenv("SPECTRUM_INGEST_MAX_POINTS", "65536")))
AUDIO_UDP_HOST = os.getenv("AUDIO_UDP_HOST", "0.0.0.0")
AUDIO_UDP_PORT = max(1, min(65535, int(os.getenv("AUDIO_UDP_PORT", "9998"))))
AUDIO_SAMPLE_RATE_HZ = max(8000, min(384000, int(os.getenv("AUDIO_SAMPLE_RATE_HZ", "48000"))))
AUDIO_MAX_QUEUE = max(1, min(512, int(os.getenv("AUDIO_MAX_QUEUE", "128"))))
AUDIO_MAX_PACKET_BYTES = max(2, min(262144, int(os.getenv("AUDIO_MAX_PACKET_BYTES", "65536"))))


RECEIVED_FRAMES = Counter("spectrum_ingest_received_frames_total", "Valid SpectrumFrames received")
INVALID_FRAMES = Counter("spectrum_ingest_invalid_frames_total", "Invalid SpectrumFrames rejected")
DROPPED_FRAMES = Counter("spectrum_ingest_dropped_frames_total", "Frames dropped for slow clients")
SEQUENCE_GAPS = Counter("spectrum_ingest_sequence_gaps_total", "Detected source sequence gaps")
CONNECTED_CLIENTS = Gauge(
    "spectrum_ingest_connected_clients", "Connected spectrum WebSocket clients"
)
SOURCE_LATENCY_MS = Gauge(
    "spectrum_ingest_source_latency_milliseconds", "Latest source frame latency in milliseconds"
)
SOURCE_FPS = Gauge("spectrum_ingest_source_fps", "Rolling valid input frame rate")
OUTGOING_FPS = Gauge("spectrum_ingest_outgoing_fps", "Rolling aggregate outgoing frame rate")
FRAME_POINTS = Histogram(
    "spectrum_ingest_frame_points",
    "SpectrumFrame point count",
    buckets=(16, 64, 128, 256, 512, 1024, 4096, 16384, 65536),
)

FRAME_BYTES = Histogram(
    "spectrum_ingest_frame_bytes",
    "Serialized SpectrumFrame byte count",
    buckets=(1024, 4096, 16384, 65536, 262144, 1048576, 4194304),
)
SOURCE_CONNECTED = Gauge(
    "spectrum_ingest_source_connected", "Whether RF Agent WebSocket is connected"
)
AUDIO_PACKETS = Counter(
    "spectrum_ingest_audio_packets_total", "Valid SDRangel PCM UDP packets received"
)
AUDIO_BYTES = Counter("spectrum_ingest_audio_bytes_total", "SDRangel PCM audio bytes received")
AUDIO_DROPPED_PACKETS = Counter(
    "spectrum_ingest_audio_dropped_packets_total", "Audio packets dropped for slow browser clients"
)
AUDIO_INVALID_PACKETS = Counter(
    "spectrum_ingest_audio_invalid_packets_total", "Invalid SDRangel PCM UDP packets rejected"
)
AUDIO_CONNECTED_CLIENTS = Gauge(
    "spectrum_ingest_audio_connected_clients", "Connected browser audio WebSocket clients"
)


@dataclass
class Metrics:
    received_frames: int = 0
    invalid_frames: int = 0
    dropped_frames: int = 0
    sequence_gaps: int = 0
    connected_clients: int = 0
    source_latency_ms: float = 0.0
    source_fps: float = 0.0
    outgoing_fps: float = 0.0
    audio_packets: int = 0
    audio_bytes: int = 0
    audio_dropped_packets: int = 0
    audio_invalid_packets: int = 0
    audio_connected_clients: int = 0


class IngestState:
    def __init__(self) -> None:
        self.metrics = Metrics()
        self.source_connected = False
        self.last_error: str | None = None
        self.last_source: dict[str, Any] | None = None
        self.last_payload: str | None = None
        self.clients: set[asyncio.Queue[str]] = set()
        self.audio_clients: set[asyncio.Queue[bytes]] = set()
        self.audio_transport: asyncio.DatagramTransport | None = None
        self.audio_last_error: str | None = None
        self.audio_last_packet_at: str | None = None
        self.last_sequences: dict[tuple[str, str, str], int] = {}
        self.received_times: deque[float] = deque(maxlen=120)
        self.outgoing_times: deque[float] = deque(maxlen=120)
        self.stop = asyncio.Event()

    def snapshot(self) -> dict[str, Any]:
        return {
            "service": "spectrum-ingest",
            "status": "connected" if self.source_connected else "degraded",
            "source_connected": self.source_connected,
            "source_url": RF_AGENT_WS_URL,
            "last_error": self.last_error,
            "last_source": self.last_source,
            "audio": {
                "transport": "udp_l16_s16le",
                "udp_listen": f"{AUDIO_UDP_HOST}:{AUDIO_UDP_PORT}",
                "sample_rate_hz": AUDIO_SAMPLE_RATE_HZ,
                "channels": 1,
                "ready": self.audio_transport is not None,
                "last_error": self.audio_last_error,
                "last_packet_at": self.audio_last_packet_at,
            },
            "metrics": asdict(self.metrics),
        }


state = IngestState()


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_frame(frame: Any) -> tuple[bool, str]:
    required = {
        "schema_version",
        "sensor_id",
        "source_type",
        "source_device",
        "device_model",
        "measurement_mode",
        "session_id",
        "timestamp",
        "sequence",
        "start_frequency_hz",
        "stop_frequency_hz",
        "step_frequency_hz",
        "center_frequency_hz",
        "sample_rate_hz",
        "rbw_hz",
        "num_points",
        "point_count",
        "power_unit",
        "powers_dbm",
        "flags",
        "metadata",
    }
    if not isinstance(frame, dict) or not required <= frame.keys():
        return False, "missing required SpectrumFrame fields"
    if frame["schema_version"] != 1 or frame["power_unit"] != "dBm":
        return False, "unsupported SpectrumFrame schema or power unit"
    if frame["source_type"] not in {"mock", "replay", "aaronia", "usrp", "hackrf"}:
        return False, "invalid source_type"
    for key in (
        "sensor_id",
        "source_device",
        "device_model",
        "measurement_mode",
        "session_id",
        "timestamp",
    ):
        if not isinstance(frame[key], str) or not frame[key]:
            return False, f"invalid {key}"
    try:
        timestamp = datetime.fromisoformat(frame["timestamp"].replace("Z", "+00:00"))
    except ValueError:
        return False, "invalid timestamp"
    if timestamp.tzinfo is None:
        return False, "timestamp timezone is required"
    integers = (
        "sequence",
        "start_frequency_hz",
        "stop_frequency_hz",
        "step_frequency_hz",
        "center_frequency_hz",
        "sample_rate_hz",
        "num_points",
    )
    if any(not isinstance(frame[key], int) or isinstance(frame[key], bool) for key in integers):
        return False, "integer frame field has invalid type"
    points = frame["num_points"]
    if (
        points <= 0
        or points > MAX_POINTS
        or frame["point_count"] != points
        or frame["step_frequency_hz"] <= 0
    ):
        return False, "invalid point count or frequency step"
    expected_stop = frame["start_frequency_hz"] + frame["step_frequency_hz"] * (points - 1)
    if frame["stop_frequency_hz"] != expected_stop:
        return False, "frequency axis is inconsistent"
    if (
        not frame["start_frequency_hz"]
        <= frame["center_frequency_hz"]
        <= frame["stop_frequency_hz"]
    ):
        return False, "center frequency is outside the frame"
    powers = frame["powers_dbm"]
    if (
        not isinstance(powers, list)
        or len(powers) != points
        or not all(_finite_number(x) for x in powers)
    ):
        return False, "powers_dbm is invalid"
    if not _finite_number(frame["rbw_hz"]) or frame["rbw_hz"] <= 0:
        return False, "rbw_hz is invalid"
    if (
        frame["source_type"] in {"mock", "replay"}
        and frame["metadata"].get("is_simulated") is not True
    ):
        return False, "simulated source is not labelled"
    return True, ""


def _rolling_fps(samples: deque[float]) -> float:
    if len(samples) < 2:
        return 0.0
    elapsed = samples[-1] - samples[0]
    return (len(samples) - 1) / elapsed if elapsed > 0 else 0.0


async def publish(payload: str) -> None:
    for queue in tuple(state.clients):
        if queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                queue.get_nowait()
                state.metrics.dropped_frames += 1
                DROPPED_FRAMES.inc()
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(payload)


class AudioDatagramProtocol(asyncio.DatagramProtocol):
    """Receives SDRangel raw mono L16/S16LE audio and fans it out to browsers."""

    def datagram_received(self, data: bytes, _address: tuple[str, int]) -> None:
        if len(data) < 2 or len(data) > AUDIO_MAX_PACKET_BYTES:
            state.metrics.audio_invalid_packets += 1
            AUDIO_INVALID_PACKETS.inc()
            return
        if len(data) % 2:
            data = data[:-1]
        if not data:
            state.metrics.audio_invalid_packets += 1
            AUDIO_INVALID_PACKETS.inc()
            return

        state.metrics.audio_packets += 1
        state.metrics.audio_bytes += len(data)
        state.audio_last_packet_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        state.audio_last_error = None
        AUDIO_PACKETS.inc()
        AUDIO_BYTES.inc(len(data))

        for queue in tuple(state.audio_clients):
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                    state.metrics.audio_dropped_packets += 1
                    AUDIO_DROPPED_PACKETS.inc()
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(data)

    def error_received(self, error: Exception) -> None:
        state.audio_last_error = f"{type(error).__name__}: {error}"

    def connection_lost(self, error: Exception | None) -> None:
        state.audio_transport = None
        if error is not None:
            state.audio_last_error = f"{type(error).__name__}: {error}"


async def consume_source() -> None:
    backoff = RECONNECT_SECONDS
    while not state.stop.is_set():
        try:
            async with websockets.connect(
                RF_AGENT_WS_URL, open_timeout=5, close_timeout=2, max_size=MAX_FRAME_BYTES
            ) as source:
                state.source_connected = True
                SOURCE_CONNECTED.set(1)
                state.last_error = None
                backoff = RECONNECT_SECONDS
                async for payload in source:
                    if not isinstance(payload, str) or len(payload.encode()) > MAX_FRAME_BYTES:
                        state.metrics.invalid_frames += 1
                        INVALID_FRAMES.inc()
                        continue
                    try:
                        frame = json.loads(payload)
                    except json.JSONDecodeError:
                        state.metrics.invalid_frames += 1
                        INVALID_FRAMES.inc()
                        continue
                    valid, error = validate_frame(frame)
                    if not valid:
                        state.metrics.invalid_frames += 1
                        INVALID_FRAMES.inc()
                        state.last_error = error
                        continue
                    key = (frame["sensor_id"], frame["session_id"], frame["source_type"])
                    previous = state.last_sequences.get(key)
                    if previous is not None and frame["sequence"] != previous + 1:
                        state.metrics.sequence_gaps += 1
                        SEQUENCE_GAPS.inc()
                    state.last_sequences[key] = frame["sequence"]
                    state.metrics.received_frames += 1
                    RECEIVED_FRAMES.inc()
                    FRAME_BYTES.observe(len(payload.encode("utf-8")))
                    FRAME_POINTS.observe(frame["num_points"])
                    now = time.monotonic()
                    state.received_times.append(now)
                    state.metrics.source_fps = _rolling_fps(state.received_times)
                    SOURCE_FPS.set(state.metrics.source_fps)
                    measured_at = datetime.fromisoformat(frame["timestamp"].replace("Z", "+00:00"))
                    state.metrics.source_latency_ms = max(
                        0.0, (datetime.now(timezone.utc) - measured_at).total_seconds() * 1000.0
                    )
                    SOURCE_LATENCY_MS.set(state.metrics.source_latency_ms)
                    state.last_source = {
                        "sensor_id": frame["sensor_id"],
                        "source_type": frame["source_type"],
                        "source_device": frame["source_device"],
                        "session_id": frame["session_id"],
                        "device_model": frame["device_model"],
                        "measurement_mode": frame["measurement_mode"],
                        "start_frequency_hz": frame["start_frequency_hz"],
                        "stop_frequency_hz": frame["stop_frequency_hz"],
                        "point_count": frame["point_count"],
                        "sequence": frame["sequence"],
                    }
                    state.last_payload = payload
                    state.last_error = None
                    await publish(payload)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            state.last_error = f"{type(error).__name__}: {error}"
        finally:
            state.source_connected = False
            SOURCE_CONNECTED.set(0)
        try:
            await asyncio.wait_for(state.stop.wait(), timeout=backoff)
        except asyncio.TimeoutError:
            backoff = min(backoff * 2.0, 30.0)


@asynccontextmanager
async def lifespan(_: FastAPI):
    state.stop.clear()
    task = asyncio.create_task(consume_source(), name="rf-agent-spectrum-consumer")
    loop = asyncio.get_running_loop()
    try:
        transport, _ = await loop.create_datagram_endpoint(
            AudioDatagramProtocol,
            local_addr=(AUDIO_UDP_HOST, AUDIO_UDP_PORT),
        )
        state.audio_transport = transport
        state.audio_last_error = None
    except OSError as error:
        state.audio_transport = None
        state.audio_last_error = f"{type(error).__name__}: {error}"
        logger.error("SDRangel audio UDP listener could not start: %s", error)
    yield
    state.stop.set()
    if state.audio_transport is not None:
        state.audio_transport.close()
        state.audio_transport = None
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="Spectrum Ingest", version="1.0.0", lifespan=lifespan)

logger = logging.getLogger("spectrum-ingest")


@app.middleware("http")
async def request_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/live")
async def live() -> dict[str, Any]:
    return {"status": "alive", "service": "spectrum-ingest"}


@app.get("/ready")
async def ready():
    snapshot = state.snapshot()
    snapshot["status"] = "ready" if state.source_connected else "not_ready"
    snapshot["required_dependency"] = "rf_agent_spectrum_websocket"
    return JSONResponse(status_code=200 if state.source_connected else 503, content=snapshot)


@app.get("/health")
async def health() -> dict[str, Any]:
    snapshot = state.snapshot()
    snapshot["health"] = "ok"
    return snapshot


@app.get("/status")
async def status() -> dict[str, Any]:
    return state.snapshot()


@app.get("/metrics")
async def metrics() -> dict[str, Any]:
    return asdict(state.metrics)


@app.get("/metrics/prometheus", include_in_schema=False)
async def prometheus_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.websocket("/ws/spectrum")
async def spectrum_socket(socket: WebSocket) -> None:
    await socket.accept()
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=MAX_QUEUE)
    state.clients.add(queue)
    if state.last_payload is not None:
        queue.put_nowait(state.last_payload)
    state.metrics.connected_clients = len(state.clients)
    CONNECTED_CLIENTS.set(state.metrics.connected_clients)
    interval = 1.0 / CLIENT_MAX_FPS
    try:
        while True:
            payload = await queue.get()
            started = time.monotonic()
            await socket.send_text(payload)
            state.outgoing_times.append(time.monotonic())
            state.metrics.outgoing_fps = _rolling_fps(state.outgoing_times)
            OUTGOING_FPS.set(state.metrics.outgoing_fps)
            await asyncio.sleep(max(0.0, interval - (time.monotonic() - started)))
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        state.clients.discard(queue)
        state.metrics.connected_clients = len(state.clients)
        CONNECTED_CLIENTS.set(state.metrics.connected_clients)


@app.websocket("/ws/status")
async def status_socket(socket: WebSocket) -> None:
    await socket.accept()
    try:
        while True:
            await socket.send_json(state.snapshot())
            await asyncio.sleep(1.0)
    except (WebSocketDisconnect, RuntimeError):
        pass


@app.websocket("/ws/audio")
async def audio_socket(socket: WebSocket) -> None:
    await socket.accept()
    queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=AUDIO_MAX_QUEUE)
    state.audio_clients.add(queue)
    state.metrics.audio_connected_clients = len(state.audio_clients)
    AUDIO_CONNECTED_CLIENTS.set(state.metrics.audio_connected_clients)
    await socket.send_json(
        {
            "schema": "pcm-s16le-v1",
            "sample_rate_hz": AUDIO_SAMPLE_RATE_HZ,
            "channels": 1,
            "endianness": "little",
        }
    )
    try:
        while True:
            await socket.send_bytes(await queue.get())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        state.audio_clients.discard(queue)
        state.metrics.audio_connected_clients = len(state.audio_clients)
        AUDIO_CONNECTED_CLIENTS.set(state.metrics.audio_connected_clients)
