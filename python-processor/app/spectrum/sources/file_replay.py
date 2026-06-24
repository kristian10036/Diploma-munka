from typing import Any

from app.config import SpectrumSettings

from .base import SpectrumFrame, SpectrumSource, SpectrumSourceUnavailable


class FileReplaySpectrumSource(SpectrumSource):
    """Placeholder for a later validated CSV/JSON spectrum replay format."""

    mode = "file_replay"

    def __init__(self, settings: SpectrumSettings):
        self.settings = settings

    def get_status(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "active": False,
            "status": "not_ready",
            "message": "File replay spectrum source is a Phase 3 stub",
        }

    async def read_frame(self) -> SpectrumFrame:
        raise SpectrumSourceUnavailable(
            "File replay input format is not implemented; no spectrum frame is available."
        )

