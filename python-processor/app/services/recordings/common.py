from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_recording_id(value: str | None) -> str:
    candidate = value or str(uuid.uuid4())
    if not _SAFE_ID.fullmatch(candidate):
        raise ValueError("invalid_recording_id")
    return candidate


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def write_json_fsync(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def write_checksum_file(path: Path, checksum: str, target_name: str) -> None:
    with path.open("w", encoding="ascii", newline="\n") as handle:
        handle.write(f"{checksum}  {target_name}\n")
        handle.flush()
        os.fsync(handle.fileno())


def finalize_directory(staging: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"recording_exists:{destination.name}")
    dir_fd = os.open(staging, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
    os.replace(staging, destination)
    parent_fd = os.open(destination.parent, os.O_RDONLY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def cleanup_staging(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
