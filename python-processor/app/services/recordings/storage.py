from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import RecordingSettings


@dataclass(frozen=True, slots=True)
class StorageStatus:
    root: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    min_free_bytes: int
    low_disk: bool
    writable: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "total_bytes": self.total_bytes,
            "used_bytes": self.used_bytes,
            "free_bytes": self.free_bytes,
            "min_free_bytes": self.min_free_bytes,
            "low_disk": self.low_disk,
            "writable": self.writable,
        }


class RecordingStorage:
    """Filesystem guardrails for all recording types.

    Retention is deliberately planning-only. Actual removal requires moving a recording
    into the quarantine directory through an explicit administrative action.
    """

    def __init__(self, settings: RecordingSettings):
        self.settings = settings

    def ensure_directories(self) -> None:
        self.settings.root.mkdir(parents=True, exist_ok=True)
        self.settings.quarantine_dir.mkdir(parents=True, exist_ok=True)

    def status(self) -> StorageStatus:
        self.ensure_directories()
        usage = shutil.disk_usage(self.settings.root)
        writable = os.access(self.settings.root, os.W_OK)
        return StorageStatus(
            root=str(self.settings.root),
            total_bytes=usage.total,
            used_bytes=usage.used,
            free_bytes=usage.free,
            min_free_bytes=self.settings.min_free_bytes,
            low_disk=usage.free < self.settings.min_free_bytes,
            writable=writable,
        )

    def assert_can_start(self, expected_bytes: int = 0) -> StorageStatus:
        if expected_bytes < 0:
            raise ValueError("expected_bytes must not be negative")
        if expected_bytes > self.settings.max_recording_bytes:
            raise RuntimeError("recording_size_limit_exceeded")
        status = self.status()
        if not status.writable:
            raise RuntimeError("recording_root_not_writable")
        if status.free_bytes - expected_bytes < self.settings.min_free_bytes:
            raise RuntimeError("recording_low_disk")
        return status

    def assert_limits(self, byte_count: int, duration_seconds: float) -> None:
        if byte_count > self.settings.max_recording_bytes:
            raise RuntimeError("recording_size_limit_exceeded")
        if duration_seconds > self.settings.max_duration_seconds:
            raise RuntimeError("recording_duration_limit_exceeded")

    def retention_plan(self, now: datetime | None = None) -> dict[str, Any]:
        """Return candidates only; never delete or move anything."""
        self.ensure_directories()
        current = now or datetime.now(timezone.utc)
        cutoff = current - timedelta(days=self.settings.retention_days)
        items: list[dict[str, Any]] = []
        for path in sorted(self.settings.root.iterdir()):
            if (
                not path.is_dir()
                or path == self.settings.quarantine_dir
                or path.name.startswith(".")
            ):
                continue
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if modified >= cutoff:
                continue
            size = sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
            items.append(
                {
                    "recording_id": path.name,
                    "path": str(path),
                    "modified_at": modified.isoformat(),
                    "size_bytes": size,
                    "action": "quarantine_candidate",
                }
            )
        return {
            "dry_run": True,
            "retention_days": self.settings.retention_days,
            "cutoff": cutoff.isoformat(),
            "candidate_count": len(items),
            "candidate_bytes": sum(item["size_bytes"] for item in items),
            "items": items,
        }
