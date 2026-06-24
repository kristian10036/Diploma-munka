from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True, slots=True)
class RecordingSettings:
    root: Path
    quarantine_dir: Path
    min_free_bytes: int
    max_recording_bytes: int
    max_duration_seconds: int
    retention_days: int

    @classmethod
    def from_env(cls) -> "RecordingSettings":
        root = Path(os.getenv("RECORDINGS_DIR", "/app/recordings")).expanduser()
        quarantine = Path(
            os.getenv("RECORDINGS_QUARANTINE_DIR", str(root / ".quarantine"))
        ).expanduser()
        return cls(
            root=root,
            quarantine_dir=quarantine,
            min_free_bytes=_positive_int("RECORDINGS_MIN_FREE_BYTES", 5 * 1024**3),
            max_recording_bytes=_positive_int("RECORDINGS_MAX_BYTES", 20 * 1024**3),
            max_duration_seconds=_positive_int("RECORDINGS_MAX_DURATION_SECONDS", 3600),
            retention_days=_positive_int("RECORDINGS_RETENTION_DAYS", 30),
        )
