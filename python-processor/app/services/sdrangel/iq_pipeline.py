from __future__ import annotations

import math
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Iterable, Protocol

PROTOCOL_VERSION = 1
SUPPORTED_SAMPLE_FORMATS = {"cf32_le", "ci16_le"}


class DataPlaneState(StrEnum):
    DISABLED = "disabled"
    NOT_CONFIGURED = "not_configured"
    CONFIGURED_NOT_TESTED = "configured_not_tested"
    CONNECTING = "connecting"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class IqPacket:
    protocol_version: int
    sample_format: str
    sample_rate_hz: int
    center_frequency_hz: int
    timestamp_ns: int
    sequence: int
    samples: tuple[complex, ...]
    packet_loss: int = 0
    overflow: int = 0

    def validate(self, max_samples: int = 1_048_576) -> None:
        if self.protocol_version != PROTOCOL_VERSION:
            raise ValueError("unsupported_iq_protocol_version")
        if self.sample_format not in SUPPORTED_SAMPLE_FORMATS:
            raise ValueError("unsupported_iq_sample_format")
        if self.sample_rate_hz <= 0 or self.center_frequency_hz <= 0:
            raise ValueError("invalid_iq_frequency_metadata")
        if self.timestamp_ns <= 0 or self.sequence < 0:
            raise ValueError("invalid_iq_sequence_metadata")
        if not self.samples or len(self.samples) > max_samples:
            raise ValueError("invalid_iq_sample_count")
        if self.packet_loss < 0 or self.overflow < 0:
            raise ValueError("negative_iq_quality_counter")
        if any(not math.isfinite(sample.real) or not math.isfinite(sample.imag) for sample in self.samples):
            raise ValueError("non_finite_iq_sample")


class IqSource(Protocol):
    def packets(self) -> Iterable[IqPacket]: ...


class IqSink(Protocol):
    def connect(self) -> None: ...
    def publish(self, packet: IqPacket) -> None: ...
    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class IqDataPlaneConfig:
    enabled: bool
    mode: str
    endpoint: str
    sample_format: str
    sample_rate_hz: int
    queue_size: int = 32
    drop_policy: str = "drop_oldest"

    @classmethod
    def from_env(cls) -> "IqDataPlaneConfig":
        enabled = os.getenv("SDRANGEL_ENABLED", "false").strip().lower() in {
            "1", "true", "yes", "on"
        }
        try:
            sample_rate = int(os.getenv("SDRANGEL_IQ_SAMPLE_RATE_HZ", "0"))
        except ValueError:
            sample_rate = 0
        try:
            queue_size = max(1, min(4096, int(os.getenv("SDRANGEL_IQ_QUEUE_SIZE", "32"))))
        except ValueError:
            queue_size = 32
        policy = os.getenv("SDRANGEL_IQ_DROP_POLICY", "drop_oldest").strip().lower()
        if policy not in {"drop_oldest", "drop_newest"}:
            policy = "drop_oldest"
        return cls(
            enabled=enabled,
            mode=os.getenv("SDRANGEL_DATA_PLANE_MODE", "not_configured").strip(),
            endpoint=os.getenv("SDRANGEL_DATA_PLANE_ENDPOINT", "").strip(),
            sample_format=os.getenv("SDRANGEL_IQ_SAMPLE_FORMAT", "cf32_le").strip(),
            sample_rate_hz=max(0, sample_rate),
            queue_size=queue_size,
            drop_policy=policy,
        )

    def initial_state(self) -> DataPlaneState:
        if not self.enabled:
            return DataPlaneState.DISABLED
        if (
            self.mode in {"", "not_configured"}
            or not self.endpoint
            or self.sample_rate_hz <= 0
            or self.sample_format not in SUPPORTED_SAMPLE_FORMATS
        ):
            return DataPlaneState.NOT_CONFIGURED
        # A concrete network transport is intentionally not assumed from the endpoint.
        return DataPlaneState.CONFIGURED_NOT_TESTED


@dataclass(slots=True)
class IqDataPlaneStats:
    packets_received: int = 0
    packets_published: int = 0
    packets_dropped: int = 0
    sequence_gaps: int = 0
    packet_loss: int = 0
    overflows: int = 0
    reconnects: int = 0
    last_sequence: int | None = None
    last_error: str | None = None
    last_packet_at_ns: int | None = None


class IqDataPlane:
    """Versioned bounded-queue IQ transport abstraction.

    This class is transport-neutral. Production code must provide a sink whose protocol
    was verified against the exact SDRangel version/plugin in use.
    """

    def __init__(self, config: IqDataPlaneConfig, sink: IqSink):
        self.config = config
        self.sink = sink
        self.state = config.initial_state()
        self.stats = IqDataPlaneStats()
        self._queue: queue.Queue[IqPacket] = queue.Queue(maxsize=config.queue_size)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def enqueue(self, packet: IqPacket) -> bool:
        packet.validate()
        self.stats.packets_received += 1
        self.stats.packet_loss += packet.packet_loss
        self.stats.overflows += packet.overflow
        if self.stats.last_sequence is not None and packet.sequence > self.stats.last_sequence + 1:
            self.stats.sequence_gaps += packet.sequence - self.stats.last_sequence - 1
        self.stats.last_sequence = packet.sequence
        self.stats.last_packet_at_ns = packet.timestamp_ns
        try:
            self._queue.put_nowait(packet)
            return True
        except queue.Full:
            self.stats.packets_dropped += 1
            if self.config.drop_policy == "drop_newest":
                return False
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                return False
            self._queue.put_nowait(packet)
            return True

    def start(self, *, allow_mock_ready: bool = False) -> None:
        if self._thread and self._thread.is_alive():
            return
        if self.state in {DataPlaneState.DISABLED, DataPlaneState.NOT_CONFIGURED}:
            raise RuntimeError(f"iq_data_plane_{self.state}")
        if self.state == DataPlaneState.CONFIGURED_NOT_TESTED and not allow_mock_ready:
            raise RuntimeError("iq_data_plane_transport_not_verified")
        self.state = DataPlaneState.CONNECTING
        self.sink.connect()
        self.state = DataPlaneState.READY
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, name="iq-data-plane", daemon=True)
        self._thread.start()

    def _worker(self) -> None:
        while not self._stop.is_set() or not self._queue.empty():
            try:
                packet = self._queue.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                self.sink.publish(packet)
                self.stats.packets_published += 1
            except Exception as exc:  # sink boundary: preserve service and expose state
                self.stats.last_error = f"{type(exc).__name__}:{exc}"
                self.state = DataPlaneState.DEGRADED
                self.stats.reconnects += 1
            finally:
                self._queue.task_done()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.sink.close()
        if self.state not in {DataPlaneState.FAILED, DataPlaneState.DEGRADED}:
            self.state = self.config.initial_state()

    def wait_until_empty(self, timeout_seconds: float = 2.0) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self._queue.unfinished_tasks == 0:
                return True
            time.sleep(0.01)
        return False

    def status(self) -> dict[str, object]:
        return {
            "implemented": True,
            "protocol_version": PROTOCOL_VERSION,
            "status": str(self.state),
            "mode": self.config.mode,
            "endpoint_configured": bool(self.config.endpoint),
            "sample_format": self.config.sample_format,
            "sample_rate_hz": self.config.sample_rate_hz,
            "queue_depth": self._queue.qsize(),
            "queue_capacity": self.config.queue_size,
            "drop_policy": self.config.drop_policy,
            "packets_received": self.stats.packets_received,
            "packets_published": self.stats.packets_published,
            "packets_dropped": self.stats.packets_dropped,
            "sequence_gaps": self.stats.sequence_gaps,
            "packet_loss": self.stats.packet_loss,
            "overflows": self.stats.overflows,
            "reconnects": self.stats.reconnects,
            "last_error": self.stats.last_error,
            "hardware_tested": False,
            "note": "No SDRangel network IQ transport is selected without a verified version/plugin profile.",
        }


class MockIqSource:
    def __init__(self, *, packet_count: int = 4, samples_per_packet: int = 64):
        self.packet_count = packet_count
        self.samples_per_packet = samples_per_packet

    def packets(self) -> Iterable[IqPacket]:
        for sequence in range(self.packet_count):
            yield IqPacket(
                protocol_version=PROTOCOL_VERSION,
                sample_format="cf32_le",
                sample_rate_hz=48_000,
                center_frequency_hz=100_000_000,
                timestamp_ns=time.time_ns() + sequence,
                sequence=sequence,
                samples=tuple(
                    complex(math.cos(2 * math.pi * n / self.samples_per_packet),
                            math.sin(2 * math.pi * n / self.samples_per_packet))
                    for n in range(self.samples_per_packet)
                ),
            )


@dataclass(slots=True)
class MockIqSink:
    packets: list[IqPacket] = field(default_factory=list)
    connected: bool = False

    def connect(self) -> None:
        self.connected = True

    def publish(self, packet: IqPacket) -> None:
        if not self.connected:
            raise RuntimeError("mock_sink_not_connected")
        self.packets.append(packet)

    def close(self) -> None:
        self.connected = False


def run_mock_pipeline(packet_count: int = 4) -> dict[str, object]:
    config = IqDataPlaneConfig(
        enabled=True,
        mode="mock",
        endpoint="memory://mock-sink",
        sample_format="cf32_le",
        sample_rate_hz=48_000,
        queue_size=max(2, packet_count),
    )
    sink = MockIqSink()
    pipeline = IqDataPlane(config, sink)
    pipeline.start(allow_mock_ready=True)
    for packet in MockIqSource(packet_count=packet_count).packets():
        pipeline.enqueue(packet)
    drained = pipeline.wait_until_empty()
    before_stop = pipeline.status()
    pipeline.stop()
    return {
        "drained": drained,
        "published": len(sink.packets),
        "status_before_stop": before_stop,
        "status_after_stop": pipeline.status(),
    }
