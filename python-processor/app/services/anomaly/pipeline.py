from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Sequence

from app.metrics import (ANOMALY_DETECTIONS_TOTAL, ANOMALY_INFERENCE_SECONDS, ML_INFERENCE_SECONDS,
    ML_QUEUE_DEPTH, ML_QUEUE_DROPS)

from .spectrum import Detection, SpectrumAnomalyDetector


@dataclass(frozen=True, slots=True)
class SpectrumEnvelope:
    frequencies_hz: tuple[int, ...]
    powers_dbm: tuple[float, ...]
    sequence: int
    timestamp: str
    source_type: str
    measurement_session_id: str | None = None
    recording_id: str | None = None


PersistCallback = Callable[[SpectrumEnvelope, list[Detection]], Awaitable[None]]


class OnlineAnomalyPipeline:
    def __init__(self, *, queue_size: int = 32, recent_limit: int = 500):
        self.detector = SpectrumAnomalyDetector()
        self.queue: asyncio.Queue[SpectrumEnvelope] = asyncio.Queue(maxsize=max(1, queue_size))
        self.recent: deque[dict[str, Any]] = deque(maxlen=recent_limit)
        self.dropped_frames = 0
        self.processed_frames = 0
        self.detection_count = 0
        self.last_error: str | None = None
        self._task: asyncio.Task | None = None
        self._persist: PersistCallback | None = None

    def set_persist_callback(self, callback: PersistCallback | None) -> None:
        self._persist = callback

    def submit_nowait(self, envelope: SpectrumEnvelope) -> bool:
        try:
            self.queue.put_nowait(envelope)
            ML_QUEUE_DEPTH.labels(pipeline="statistical_baseline").set(self.queue.qsize())
            return True
        except asyncio.QueueFull:
            self.dropped_frames += 1
            ML_QUEUE_DROPS.labels(pipeline="statistical_baseline").set(self.dropped_frames)
            return False

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._worker(), name="online-anomaly-pipeline")

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _worker(self) -> None:
        while True:
            envelope = await self.queue.get()
            try:
                started = time.perf_counter()
                detections = await asyncio.to_thread(
                    self.detector.process,
                    envelope.frequencies_hz,
                    envelope.powers_dbm,
                    sequence=envelope.sequence,
                    source_type=envelope.source_type,
                    timestamp=envelope.timestamp,
                )
                duration = time.perf_counter() - started
                ANOMALY_INFERENCE_SECONDS.observe(duration)
                ML_INFERENCE_SECONDS.labels(pipeline="statistical_baseline").observe(duration)
                self.processed_frames += 1
                self.detection_count += len(detections)
                for detection in detections:
                    ANOMALY_DETECTIONS_TOTAL.labels(
                        domain=detection.entity_domain,
                        class_name=detection.class_name,
                        severity=detection.severity,
                    ).inc()
                    self.recent.appendleft(detection.as_dict())
                if detections and self._persist:
                    try:
                        await self._persist(envelope, detections)
                    except Exception as exc:
                        self.last_error = f"persist:{type(exc).__name__}:{exc}"
            except Exception as exc:
                self.last_error = f"process:{type(exc).__name__}:{exc}"
            finally:
                self.queue.task_done()
                ML_QUEUE_DEPTH.labels(pipeline="statistical_baseline").set(self.queue.qsize())

    def status(self) -> dict[str, Any]:
        return {
            "implemented": True,
            "status": "running" if self._task and not self._task.done() else "stopped",
            "queue_depth": self.queue.qsize(),
            "queue_capacity": self.queue.maxsize,
            "dropped_frames": self.dropped_frames,
            "processed_frames": self.processed_frames,
            "detection_count": self.detection_count,
            "recent_count": len(self.recent),
            "last_error": self.last_error,
            "detector": self.detector.status(),
            "ml_model_required": False,
        }
