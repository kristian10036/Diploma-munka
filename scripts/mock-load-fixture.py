#!/usr/bin/env python3
"""Offline, deterministic load fixture for the hardware-independent data path.

This is not a hardware benchmark. It measures the current machine and writes all
inputs/environment into the report so the numbers cannot be mistaken for an
Aaronia/USRP performance claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import queue
import statistics
import sys
import tempfile
import time
import tracemalloc
import types
from datetime import datetime, timezone
from importlib.machinery import ModuleSpec
from importlib.util import find_spec
from pathlib import Path

import numpy as np

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
    prometheus_client.generate_latest = lambda: b""
    sys.modules["prometheus_client"] = prometheus_client

from app.services.anomaly.spectrum import SpectrumAnomalyDetector


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--points", type=int, default=65_536)
    parser.add_argument("--frames", type=int, default=32)
    parser.add_argument("--clients", type=int, default=4)
    parser.add_argument("--client-queue", type=int, default=2)
    parser.add_argument("--slow-client-drain-every", type=int, default=6)
    parser.add_argument("--anomaly", choices=("on", "off"), default="on")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 2 <= args.points <= 65_536:
        parser.error("--points must be between 2 and 65536")
    if not 1 <= args.frames <= 10_000:
        parser.error("--frames must be between 1 and 10000")
    if not 1 <= args.clients <= 128:
        parser.error("--clients must be between 1 and 128")

    start_hz = 100_000_000
    step_hz = 1_000
    frequencies = np.arange(args.points, dtype=np.int64) * step_hz + start_hz
    base = np.full(args.points, -96.0, dtype=np.float64)
    queues = [queue.Queue(maxsize=max(1, args.client_queue)) for _ in range(args.clients)]
    client_drops = [0 for _ in queues]
    detector = SpectrumAnomalyDetector() if args.anomaly == "on" else None
    serialize_seconds: list[float] = []
    detector_seconds: list[float] = []
    payload_sizes: list[int] = []
    detection_count = 0

    output = args.output or Path(tempfile.gettempdir()) / f"dm-load-fixture-{int(time.time())}.json"
    recording_path = output.with_suffix(".ndjson")
    output.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()

    tracemalloc.start()
    wall_started = time.perf_counter()
    with recording_path.open("wb") as recording:
        for sequence in range(args.frames):
            powers = base.copy()
            # Deterministic narrowband event after detector warm-up.
            if sequence >= 8 and sequence % 7 == 0:
                center = args.points // 2
                powers[max(0, center - 2) : min(args.points, center + 3)] = -42.0
            frame = {
                "schema_version": 1,
                "sensor_id": "offline-load-fixture",
                "source_type": "mock",
                "source_device": "numpy-generator",
                "session_id": "offline-load-fixture",
                "timestamp": iso_now(),
                "sequence": sequence,
                "start_frequency_hz": int(frequencies[0]),
                "stop_frequency_hz": int(frequencies[-1]),
                "step_frequency_hz": step_hz,
                "center_frequency_hz": int(frequencies[len(frequencies) // 2]),
                "sample_rate_hz": step_hz * args.points,
                "rbw_hz": float(step_hz),
                "num_points": args.points,
                "power_unit": "dBm",
                "powers_dbm": powers.tolist(),
                "flags": {"overflow": False, "dropped": False, "inaccurate": False},
                "metadata": {"is_simulated": True, "fixture": True},
            }
            started = time.perf_counter()
            payload = (json.dumps(frame, separators=(",", ":"), allow_nan=False) + "\n").encode(
                "utf-8"
            )
            serialize_seconds.append(time.perf_counter() - started)
            payload_sizes.append(len(payload))
            recording.write(payload)
            digest.update(payload)

            for index, client_queue in enumerate(queues):
                try:
                    client_queue.put_nowait(payload)
                except queue.Full:
                    client_drops[index] += 1
                # Client zero is intentionally slow; the others drain every frame.
                should_drain = index != 0 or sequence % max(1, args.slow_client_drain_every) == 0
                if should_drain:
                    try:
                        client_queue.get_nowait()
                        client_queue.task_done()
                    except queue.Empty:
                        pass

            if detector is not None:
                started = time.perf_counter()
                detections = detector.process(
                    frequencies,
                    powers,
                    sequence=sequence,
                    source_type="mock",
                    timestamp=frame["timestamp"],
                )
                detector_seconds.append(time.perf_counter() - started)
                detection_count += len(detections)
        recording.flush()
        os.fsync(recording.fileno())

    wall_seconds = time.perf_counter() - wall_started
    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    report = {
        "report_version": 1,
        "generated_at": iso_now(),
        "scope": "offline_mock_fixture_not_hardware_benchmark",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
        },
        "configuration": {
            "points": args.points,
            "frames": args.frames,
            "clients": args.clients,
            "client_queue": args.client_queue,
            "slow_client_drain_every": args.slow_client_drain_every,
            "anomaly": args.anomaly,
        },
        "measured": {
            "wall_seconds": wall_seconds,
            "frames_per_second": args.frames / wall_seconds if wall_seconds else None,
            "payload_bytes_mean": statistics.fmean(payload_sizes),
            "payload_bytes_max": max(payload_sizes),
            "serialization_ms_mean": statistics.fmean(serialize_seconds) * 1000,
            "serialization_ms_p95": percentile(serialize_seconds, 0.95) * 1000,
            "anomaly_ms_mean": statistics.fmean(detector_seconds) * 1000
            if detector_seconds
            else None,
            "anomaly_ms_p95": percentile(detector_seconds, 0.95) * 1000
            if detector_seconds
            else None,
            "detections": detection_count,
            "client_drops": client_drops,
            "peak_tracemalloc_bytes": peak_memory,
            "recording_bytes": recording_path.stat().st_size,
            "recording_sha256": digest.hexdigest(),
        },
        "artifacts": {"recording": str(recording_path), "report": str(output)},
    }
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
