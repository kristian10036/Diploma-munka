from typing import Any

from app.config import SpectrumSettings

from .sources.aaronia_rtsa import AaroniaRTSAHTTPSource
from .sources.base import SpectrumFrame, SpectrumSource, SpectrumSourceUnavailable
from .sources.file_replay import FileReplaySpectrumSource
from .sources.simulator import SimulatorSpectrumSource
from .sources.spectrum_ingest import SpectrumIngestWebSocketSource


class SpectrumSourceManager:
    def __init__(self, settings: SpectrumSettings):
        self.settings = settings
        self.sources: dict[str, SpectrumSource] = {
            "simulator": SimulatorSpectrumSource(settings),
            "aaronia_rtsa": AaroniaRTSAHTTPSource(settings),
            "file_replay": FileReplaySpectrumSource(settings),
            "spectrum_ingest": SpectrumIngestWebSocketSource(settings),
        }
        self.active_source = self.sources.get(settings.source_mode)

    def get_status(self) -> dict[str, Any]:
        if self.active_source is None:
            status: dict[str, Any] = {
                "mode": self.settings.source_mode,
                "active": False,
                "status": "error",
                "message": (
                    "Unsupported spectrum source mode. Expected simulator, "
                    "aaronia_rtsa, spectrum_ingest or file_replay."
                ),
            }
        else:
            status = self.active_source.get_status()
        if self.settings.warnings:
            status["config_warnings"] = list(self.settings.warnings)
        return status

    async def refresh_status(self) -> dict[str, Any]:
        if isinstance(self.active_source, AaroniaRTSAHTTPSource):
            await self.active_source.probe()
        return self.get_status()

    async def read_frame(self) -> SpectrumFrame:
        if self.active_source is None:
            raise SpectrumSourceUnavailable(
                f"Unsupported spectrum source mode: {self.settings.source_mode}"
            )
        return await self.active_source.read_frame()
