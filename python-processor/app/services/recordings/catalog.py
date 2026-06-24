from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .common import sha256_file
from .config import RecordingSettings
from .storage import RecordingStorage


class RecordingCatalog:
    def __init__(self, settings: RecordingSettings):
        self.settings = settings
        self.storage = RecordingStorage(settings)

    @staticmethod
    def _verify(directory: Path, metadata: dict[str, Any]) -> str:
        checksum = str(metadata.get("checksum_sha256") or "")
        if len(checksum) != 64:
            return "missing"
        recording_type = metadata.get("recording_type", "spectrum")
        if recording_type == "iq":
            name = metadata.get("data_file")
        elif recording_type == "audio":
            name = metadata.get("audio_file")
        else:
            name = metadata.get("frame_file")
        if not name:
            return "missing"
        target = directory / str(name)
        if not target.is_file():
            return "missing"
        return "valid" if sha256_file(target) == checksum else "invalid"

    def list(self, *, verify_checksums: bool = False, limit: int = 500) -> list[dict[str, Any]]:
        self.storage.ensure_directories()
        items: list[dict[str, Any]] = []
        for directory in self.settings.root.iterdir():
            if not directory.is_dir() or directory.name.startswith("."):
                continue
            metadata_path = directory / "metadata.json"
            if not metadata_path.is_file():
                items.append(
                    {
                        "recording_id": directory.name,
                        "recording_type": "unknown",
                        "status": "incomplete",
                        "checksum_status": "not_checked",
                        "path": str(directory),
                    }
                )
                continue
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                items.append(
                    {
                        "recording_id": directory.name,
                        "recording_type": "unknown",
                        "status": "corrupt_metadata",
                        "checksum_status": "not_checked",
                        "error": type(exc).__name__,
                    }
                )
                continue
            item = dict(metadata)
            item.setdefault("recording_id", directory.name)
            item.setdefault("recording_type", "spectrum")
            item.setdefault("status", "completed")
            item["checksum_status"] = self._verify(directory, item) if verify_checksums else "not_checked"
            items.append(item)
        items.sort(key=lambda value: str(value.get("started_at") or ""), reverse=True)
        return items[: max(1, min(limit, 1000))]
