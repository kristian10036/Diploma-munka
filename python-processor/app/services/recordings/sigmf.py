from __future__ import annotations

import json
import math
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from app.metrics import RECORDING_BYTES_TOTAL, RECORDING_FRAMES_TOTAL, RECORDING_ITEMS_TOTAL

from .common import (
    cleanup_staging,
    finalize_directory,
    safe_recording_id,
    sha256_file,
    utc_now_iso,
    write_checksum_file,
    write_json_fsync,
)
from .config import RecordingSettings
from .storage import RecordingStorage

_SUPPORTED_DATATYPES = {"cf32_le": ("<ff", 8), "ci16_le": ("<hh", 4)}


@dataclass(frozen=True, slots=True)
class IqSample:
    i: float
    q: float


class SigMfRecordingWriter:
    """Atomic SigMF-compatible IQ recording writer for mock and future sources."""

    def __init__(
        self,
        settings: RecordingSettings,
        *,
        recording_id: str | None,
        datatype: str,
        sample_rate: float,
        center_frequency_hz: int,
        source: str,
        device: str,
        timestamp: str | None = None,
        session_id: str | None = None,
        antenna: str | None = None,
        downconverter: str | None = None,
        packet_loss: int = 0,
        overflow_count: int = 0,
    ):
        if datatype not in _SUPPORTED_DATATYPES:
            raise ValueError("unsupported_sigmf_datatype")
        if not math.isfinite(sample_rate) or sample_rate <= 0:
            raise ValueError("invalid_sample_rate")
        if center_frequency_hz <= 0:
            raise ValueError("invalid_center_frequency")
        if packet_loss < 0 or overflow_count < 0:
            raise ValueError("negative_quality_counter")
        self.settings = settings
        self.storage = RecordingStorage(settings)
        self.recording_id = safe_recording_id(recording_id)
        self.datatype = datatype
        self.sample_rate = float(sample_rate)
        self.center_frequency_hz = int(center_frequency_hz)
        self.source = source
        self.device = device
        self.timestamp = timestamp or utc_now_iso()
        self.session_id = session_id
        self.antenna = antenna
        self.downconverter = downconverter
        self.packet_loss = packet_loss
        self.overflow_count = overflow_count
        self.sample_count = 0
        self._closed = False
        self._started_at = utc_now_iso()
        self._destination = settings.root / self.recording_id
        self._staging = settings.root / f".{self.recording_id}.partial"
        self.storage.assert_can_start()
        cleanup_staging(self._staging)
        self._staging.mkdir(parents=True)
        self._data_name = f"{self.recording_id}.sigmf-data"
        self._meta_name = f"{self.recording_id}.sigmf-meta"
        self._data_path = self._staging / self._data_name
        self._handle = self._data_path.open("wb")

    @property
    def destination(self) -> Path:
        return self._destination

    def write(self, samples: Iterable[complex | Sequence[float] | IqSample]) -> int:
        if self._closed:
            raise RuntimeError("recording_already_closed")
        fmt, bytes_per_sample = _SUPPORTED_DATATYPES[self.datatype]
        written = 0
        for value in samples:
            if isinstance(value, complex):
                i_value, q_value = value.real, value.imag
            elif isinstance(value, IqSample):
                i_value, q_value = value.i, value.q
            else:
                if len(value) != 2:
                    raise ValueError("iq_sample_requires_two_components")
                i_value, q_value = float(value[0]), float(value[1])
            if not math.isfinite(float(i_value)) or not math.isfinite(float(q_value)):
                raise ValueError("non_finite_iq_sample")
            if self.datatype == "cf32_le":
                payload = struct.pack(fmt, float(i_value), float(q_value))
            else:
                i_int = max(-32768, min(32767, int(round(float(i_value)))))
                q_int = max(-32768, min(32767, int(round(float(q_value)))))
                payload = struct.pack(fmt, i_int, q_int)
            self._handle.write(payload)
            written += 1
        self.sample_count += written
        byte_count = self.sample_count * bytes_per_sample
        duration = self.sample_count / self.sample_rate
        self.storage.assert_limits(byte_count, duration)
        return written

    def close(self) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError("recording_already_closed")
        self._closed = True
        try:
            self._handle.flush()
            os.fsync(self._handle.fileno())
            self._handle.close()
            checksum = sha256_file(self._data_path)
            duration = self.sample_count / self.sample_rate
            metadata: dict[str, Any] = {
                "global": {
                    "core:datatype": self.datatype,
                    "core:sample_rate": self.sample_rate,
                    "core:version": "1.0.0",
                    "core:recorder": "DM RF/TSCM platform",
                    "core:description": (
                        "IQ recording; mock-only unless source metadata states hardware"
                    ),
                    "dm:recording_id": self.recording_id,
                    "dm:recording_type": "iq",
                    "dm:session_id": self.session_id,
                    "dm:source": self.source,
                    "dm:device": self.device,
                    "dm:antenna": self.antenna,
                    "dm:downconverter": self.downconverter,
                    "dm:checksum_algorithm": "sha256",
                    "dm:checksum_sha256": checksum,
                    "dm:packet_loss": self.packet_loss,
                    "dm:overflow_count": self.overflow_count,
                    "dm:status": "completed",
                },
                "captures": [
                    {
                        "core:sample_start": 0,
                        "core:frequency": self.center_frequency_hz,
                        "core:datetime": self.timestamp,
                    }
                ],
                "annotations": [],
            }
            write_json_fsync(self._staging / self._meta_name, metadata)
            write_checksum_file(self._staging / "checksum.sha256", checksum, self._data_name)
            summary = {
                "schema_version": 1,
                "recording_id": self.recording_id,
                "recording_type": "iq",
                "status": "completed",
                "source": self.source,
                "source_device": self.device,
                "started_at": self._started_at,
                "ended_at": utc_now_iso(),
                "datatype": self.datatype,
                "sample_rate": self.sample_rate,
                "center_frequency_hz": self.center_frequency_hz,
                "sample_count": self.sample_count,
                "duration_seconds": duration,
                "data_file": self._data_name,
                "metadata_file": self._meta_name,
                "size_bytes": self._data_path.stat().st_size,
                "checksum_algorithm": "sha256",
                "checksum_sha256": checksum,
                "checksum_status": "valid",
                "packet_loss": self.packet_loss,
                "overflow_count": self.overflow_count,
                "mock": self.source == "mock",
            }
            write_json_fsync(self._staging / "metadata.json", summary)
            finalize_directory(self._staging, self._destination)
            RECORDING_BYTES_TOTAL.labels(recording_type="iq").inc(summary["size_bytes"])
            RECORDING_FRAMES_TOTAL.labels(recording_type="iq").inc(self.sample_count)
            RECORDING_ITEMS_TOTAL.labels(recording_type="iq", result="completed").inc()
            return summary
        except Exception:
            RECORDING_ITEMS_TOTAL.labels(recording_type="iq", result="failed").inc()
            try:
                if not self._handle.closed:
                    self._handle.close()
            finally:
                cleanup_staging(self._staging)
            raise

    def abort(self) -> None:
        if not self._closed:
            self._closed = True
            self._handle.close()
        cleanup_staging(self._staging)

    def __enter__(self) -> "SigMfRecordingWriter":
        return self

    def __exit__(self, exc_type, exc, _tb) -> None:
        if exc_type is None:
            self.close()
        else:
            self.abort()


class SigMfRecordingReader:
    def __init__(self, directory: Path):
        self.directory = directory
        summary_path = directory / "metadata.json"
        if not summary_path.is_file():
            raise ValueError("missing_recording_metadata")
        self.summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if self.summary.get("recording_type") != "iq":
            raise ValueError("not_iq_recording")
        self.data_path = directory / str(self.summary["data_file"])
        self.sigmf_meta_path = directory / str(self.summary["metadata_file"])
        if not self.data_path.is_file() or not self.sigmf_meta_path.is_file():
            raise ValueError("incomplete_iq_recording")
        self.sigmf_metadata = json.loads(self.sigmf_meta_path.read_text(encoding="utf-8"))
        self.datatype = str(self.summary["datatype"])
        if self.datatype not in _SUPPORTED_DATATYPES:
            raise ValueError("unsupported_sigmf_datatype")

    def verify_checksum(self) -> bool:
        expected = str(self.summary.get("checksum_sha256") or "")
        return len(expected) == 64 and sha256_file(self.data_path) == expected

    def samples(self) -> Iterator[complex]:
        fmt, size = _SUPPORTED_DATATYPES[self.datatype]
        with self.data_path.open("rb") as handle:
            while payload := handle.read(size):
                if len(payload) != size:
                    raise ValueError("truncated_iq_recording")
                i_value, q_value = struct.unpack(fmt, payload)
                yield complex(i_value, q_value)


def create_mock_iq_recording(
    settings: RecordingSettings,
    *,
    recording_id: str | None = None,
    sample_rate: float = 48_000.0,
    center_frequency_hz: int = 100_000_000,
    sample_count: int = 4096,
    tone_hz: float = 1000.0,
) -> dict[str, Any]:
    if sample_count <= 0:
        raise ValueError("sample_count must be positive")
    writer = SigMfRecordingWriter(
        settings,
        recording_id=recording_id,
        datatype="cf32_le",
        sample_rate=sample_rate,
        center_frequency_hz=center_frequency_hz,
        source="mock",
        device="deterministic-iq-generator",
    )
    try:
        samples = (
            complex(
                math.cos(2 * math.pi * tone_hz * n / sample_rate),
                math.sin(2 * math.pi * tone_hz * n / sample_rate),
            )
            for n in range(sample_count)
        )
        writer.write(samples)
        return writer.close()
    except Exception:
        writer.abort()
        raise
