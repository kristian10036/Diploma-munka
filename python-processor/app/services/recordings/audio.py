from __future__ import annotations

import json
import math
import os
import struct
import wave
from pathlib import Path
from typing import Any, Iterable

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


class AudioRecordingWriter:
    """Atomic mono/stereo PCM16 WAV writer with sidecar metadata."""

    def __init__(
        self,
        settings: RecordingSettings,
        *,
        recording_id: str | None,
        sample_rate: int,
        channels: int = 1,
        source: str = "mock",
        demodulation: str = "unknown",
        center_frequency_hz: int | None = None,
        session_id: str | None = None,
    ):
        if sample_rate <= 0:
            raise ValueError("invalid_audio_sample_rate")
        if channels not in (1, 2):
            raise ValueError("unsupported_audio_channel_count")
        self.settings = settings
        self.storage = RecordingStorage(settings)
        self.recording_id = safe_recording_id(recording_id)
        self.sample_rate = int(sample_rate)
        self.channels = channels
        self.source = source
        self.demodulation = demodulation
        self.center_frequency_hz = center_frequency_hz
        self.session_id = session_id
        self.frame_count = 0
        self._closed = False
        self._started_at = utc_now_iso()
        self._destination = settings.root / self.recording_id
        self._staging = settings.root / f".{self.recording_id}.partial"
        self.storage.assert_can_start()
        cleanup_staging(self._staging)
        self._staging.mkdir(parents=True)
        self._wav_name = "audio.wav"
        self._wav_path = self._staging / self._wav_name
        self._handle = wave.open(str(self._wav_path), "wb")
        self._handle.setnchannels(channels)
        self._handle.setsampwidth(2)
        self._handle.setframerate(sample_rate)

    def write(self, samples: Iterable[float | int]) -> int:
        if self._closed:
            raise RuntimeError("recording_already_closed")
        payload = bytearray()
        count = 0
        for value in samples:
            if isinstance(value, float):
                if not math.isfinite(value):
                    raise ValueError("non_finite_audio_sample")
                pcm = int(round(max(-1.0, min(1.0, value)) * 32767))
            else:
                pcm = max(-32768, min(32767, int(value)))
            payload.extend(struct.pack("<h", pcm))
            count += 1
        if count % self.channels:
            raise ValueError("audio_samples_not_aligned_to_channels")
        self._handle.writeframesraw(bytes(payload))
        frames = count // self.channels
        self.frame_count += frames
        duration = self.frame_count / self.sample_rate
        self.storage.assert_limits(self.frame_count * self.channels * 2, duration)
        return frames

    def close(self) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError("recording_already_closed")
        self._closed = True
        try:
            self._handle.close()
            with self._wav_path.open("rb") as handle:
                os.fsync(handle.fileno())
            checksum = sha256_file(self._wav_path)
            duration = self.frame_count / self.sample_rate
            summary = {
                "schema_version": 1,
                "recording_id": self.recording_id,
                "recording_type": "audio",
                "status": "completed",
                "source": self.source,
                "session_id": self.session_id,
                "started_at": self._started_at,
                "ended_at": utc_now_iso(),
                "audio_file": self._wav_name,
                "format": "wav_pcm_s16le",
                "sample_rate": self.sample_rate,
                "channels": self.channels,
                "frame_count": self.frame_count,
                "duration_seconds": duration,
                "demodulation": self.demodulation,
                "center_frequency_hz": self.center_frequency_hz,
                "size_bytes": self._wav_path.stat().st_size,
                "checksum_algorithm": "sha256",
                "checksum_sha256": checksum,
                "checksum_status": "valid",
                "mock": self.source == "mock",
                "hardware_tested": False,
            }
            write_json_fsync(self._staging / "metadata.json", summary)
            write_checksum_file(self._staging / "checksum.sha256", checksum, self._wav_name)
            finalize_directory(self._staging, self._destination)
            RECORDING_BYTES_TOTAL.labels(recording_type="audio").inc(summary["size_bytes"])
            RECORDING_FRAMES_TOTAL.labels(recording_type="audio").inc(self.frame_count)
            RECORDING_ITEMS_TOTAL.labels(recording_type="audio", result="completed").inc()
            return summary
        except Exception:
            RECORDING_ITEMS_TOTAL.labels(recording_type="audio", result="failed").inc()
            cleanup_staging(self._staging)
            raise

    def abort(self) -> None:
        if not self._closed:
            self._closed = True
            self._handle.close()
        cleanup_staging(self._staging)


class AudioRecordingReader:
    def __init__(self, directory: Path):
        self.directory = directory
        metadata_path = directory / "metadata.json"
        if not metadata_path.is_file():
            raise ValueError("missing_recording_metadata")
        self.metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if self.metadata.get("recording_type") != "audio":
            raise ValueError("not_audio_recording")
        self.audio_path = directory / str(self.metadata["audio_file"])
        if not self.audio_path.is_file():
            raise ValueError("incomplete_audio_recording")

    def verify_checksum(self) -> bool:
        expected = str(self.metadata.get("checksum_sha256") or "")
        return len(expected) == 64 and sha256_file(self.audio_path) == expected

    def properties(self) -> dict[str, int]:
        with wave.open(str(self.audio_path), "rb") as handle:
            return {
                "channels": handle.getnchannels(),
                "sample_width": handle.getsampwidth(),
                "sample_rate": handle.getframerate(),
                "frame_count": handle.getnframes(),
            }


def create_mock_audio_recording(
    settings: RecordingSettings,
    *,
    recording_id: str | None = None,
    sample_rate: int = 48_000,
    duration_seconds: float = 0.1,
    tone_hz: float = 1000.0,
) -> dict[str, Any]:
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    writer = AudioRecordingWriter(
        settings,
        recording_id=recording_id,
        sample_rate=sample_rate,
        source="mock",
        demodulation="mock_tone",
    )
    try:
        sample_count = max(1, int(round(sample_rate * duration_seconds)))
        writer.write(
            0.25 * math.sin(2 * math.pi * tone_hz * n / sample_rate) for n in range(sample_count)
        )
        return writer.close()
    except Exception:
        writer.abort()
        raise
