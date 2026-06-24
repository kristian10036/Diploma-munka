from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import numpy as np

from .classifier import RF_CLASSES
from .preprocessing import SpectrogramPreprocessor


LABEL_QUALITIES = {"ground_truth", "controlled_simulation", "weak_label"}


@dataclass(frozen=True)
class RecordingLabel:
    recording_path: Path
    label: str
    label_quality: str
    provenance: str

    def validate(self, allow_weak_labels: bool = False) -> None:
        if self.label not in RF_CLASSES:
            raise ValueError(f"unsupported RF class: {self.label}")
        if self.label_quality not in LABEL_QUALITIES:
            raise ValueError(f"unsupported label_quality: {self.label_quality}")
        if self.label_quality == "weak_label" and not allow_weak_labels:
            raise ValueError("weak labels are excluded from training by default")
        if not self.provenance.strip():
            raise ValueError("label provenance is required")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _frame_lines(path: Path) -> Iterator[str]:
    if path.suffix != ".zst":
        with path.open(encoding="utf-8") as source:
            yield from source
        return
    process = subprocess.Popen(
        ["zstd", "-q", "-dc", "--", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    assert process.stdout is not None
    try:
        yield from process.stdout
    finally:
        process.stdout.close()
        stderr = process.stderr.read() if process.stderr else ""
        return_code = process.wait()
        if return_code != 0:
            raise ValueError(f"zstd decompression failed: {stderr.strip()}")


def load_recording(recording_directory: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    metadata_path = recording_directory / "metadata.json"
    checksum_path = recording_directory / "checksum.sha256"
    if not metadata_path.is_file() or not checksum_path.is_file():
        raise ValueError("recording metadata or checksum is missing")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("schema_version") != 1:
        raise ValueError("unsupported recording schema_version")
    frame_file = str(metadata.get("frame_file", "frames.ndjson.zst"))
    if frame_file not in {"frames.ndjson", "frames.ndjson.zst"}:
        raise ValueError("unsupported frame_file")
    frame_path = recording_directory / frame_file
    if not frame_path.is_file():
        raise ValueError("recording frame file is missing")
    checksum_parts = checksum_path.read_text(encoding="ascii").split()
    if len(checksum_parts) < 1 or len(checksum_parts[0]) != 64:
        raise ValueError("invalid checksum file")
    if _sha256(frame_path) != checksum_parts[0].lower():
        raise ValueError("recording checksum mismatch")

    frames: list[dict[str, Any]] = []
    dropped = 0
    for line in _frame_lines(frame_path):
        if not line.strip():
            continue
        if len(line.encode()) > 8 * 1024 * 1024:
            dropped += 1
            continue
        try:
            value = json.loads(line)
            SpectrogramPreprocessor._validate_frame(value)
            frames.append(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            dropped += 1
        if len(frames) + dropped > 100_000:
            raise ValueError("recording exceeds the frame limit")
    expected = int(metadata.get("frame_count", len(frames) + dropped))
    if expected != len(frames) + dropped:
        raise ValueError("recording frame_count mismatch")
    if not frames:
        raise ValueError("recording contains no valid SpectrumFrame")
    metadata["valid_frame_count"] = len(frames)
    metadata["dropped_frame_count"] = dropped
    return metadata, frames


def build_recording_windows(
    recording: RecordingLabel,
    output_directory: Path,
    time_bins: int = 32,
    frequency_bins: int = 256,
    stride: int = 16,
    allow_weak_labels: bool = False,
) -> list[dict[str, Any]]:
    recording.validate(allow_weak_labels=allow_weak_labels)
    if stride < 1 or stride > time_bins:
        raise ValueError("stride must be between 1 and time_bins")
    metadata, frames = load_recording(recording.recording_path)
    if len(frames) < time_bins:
        raise ValueError("recording is shorter than one spectrogram window")
    recording_id = str(metadata.get("recording_id") or recording.recording_path.name)
    session_id = str(metadata.get("session_id") or frames[0]["session_id"])
    preprocessor = SpectrogramPreprocessor(frequency_bins=frequency_bins, time_bins=time_bins)
    output_directory.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for start in range(0, len(frames) - time_bins + 1, stride):
        window = frames[start : start + time_bins]
        prepared = preprocessor.prepare(window)
        item_id = f"{recording_id}-{start:08d}"
        output_path = output_directory / f"{item_id}.npz"
        temporary = output_path.with_suffix(".npz.tmp")
        with temporary.open("wb") as target:
            np.savez_compressed(
                target,
                spectrogram=prepared.normalized,
                frequencies_hz=prepared.frequencies_hz,
                label=np.asarray(recording.label),
            )
        temporary.replace(output_path)
        entries.append(
            {
                "item_id": item_id,
                "recording_id": recording_id,
                "session_id": session_id,
                "label": recording.label,
                "label_quality": recording.label_quality,
                "provenance": recording.provenance,
                "source_type": metadata.get("source_type", frames[0]["source_type"]),
                "processed_path": str(output_path),
                "first_sequence": window[0].get("sequence"),
                "last_sequence": window[-1].get("sequence"),
                "first_timestamp": window[0].get("timestamp"),
                "last_timestamp": window[-1].get("timestamp"),
            }
        )
    return entries
