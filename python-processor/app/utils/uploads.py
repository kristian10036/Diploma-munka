from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile

MIB = 1024 * 1024
DEFAULT_IMPORT_LIMIT_BYTES = 50 * MIB
REFERENCE_IMPORT_LIMIT_BYTES = 64 * MIB
REFERENCE_IMAGE_LIMIT_BYTES = 20 * MIB


@dataclass(frozen=True, slots=True)
class DetectedImage:
    content_type: str
    suffix: str


def read_bounded_upload(
    file: UploadFile,
    *,
    max_bytes: int,
    empty_detail: str | dict,
    too_large_detail: str | dict,
) -> bytes:
    """Read one upload without allowing an unbounded in-memory allocation.

    The extra byte makes the limit deterministic without trusting the client
    supplied Content-Length header. The upload stream is intentionally read
    once; callers should pass the returned bytes to parsers and persistence.
    """

    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    payload = file.file.read(max_bytes + 1)
    if not payload:
        raise HTTPException(status_code=400, detail=empty_detail)
    if len(payload) > max_bytes:
        raise HTTPException(status_code=413, detail=too_large_detail)
    return payload


def reject_binary_text_payload(payload: bytes, *, label: str = "A feltoltott fajl") -> None:
    """Reject obvious binary data before a CSV/JSON parser sees it.

    CSV imports still support UTF-8 and legacy Latin-1 text. NUL bytes are not
    valid in those inputs and are a reliable sign that a binary file was
    uploaded under a misleading extension or MIME type.
    """

    if b"\x00" in payload[:8192]:
        raise HTTPException(status_code=415, detail=f"{label} nem szoveges CSV/JSON allomany.")


def detect_reference_image(payload: bytes, filename: str = "") -> DetectedImage:
    """Identify the two intentionally supported reference image formats.

    Detection is based on magic bytes, not a client-controlled MIME header or
    file extension. Deep image decoding is left to the browser; this boundary
    only prevents arbitrary files from being stored as reference images.
    """

    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return DetectedImage(content_type="image/png", suffix=".png")
    if payload.startswith(b"BM"):
        return DetectedImage(content_type="image/bmp", suffix=".bmp")
    suffix = Path(filename).suffix.lower()
    raise HTTPException(
        status_code=415,
        detail=f"A referencia kep tenyleges formatuma nem tamogatott ({suffix or 'ismeretlen'}). Csak PNG vagy BMP engedelyezett.",
    )
