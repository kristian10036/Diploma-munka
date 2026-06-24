from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class SpectrumPoint:
    frequency_mhz: float
    power_dbm: float

    def to_websocket_dict(self) -> dict[str, float]:
        return {
            "x": round(float(self.frequency_mhz), 6),
            "y": round(float(self.power_dbm), 2),
        }


@dataclass(frozen=True)
class SpectrumFrame:
    timestamp: datetime
    source_mode: str
    points: tuple[SpectrumPoint, ...]
    sequence: int | None = None
    source_device: str | None = None
    device_model: str | None = None
    measurement_mode: str | None = None
    flags: dict[str, bool] | None = None


class SpectrumSourceUnavailable(RuntimeError):
    """Raised when a configured source cannot currently provide a real frame."""


class SpectrumSource(ABC):
    mode: str

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        """Return a JSON-serializable status without claiming unavailable data."""

    @abstractmethod
    async def read_frame(self) -> SpectrumFrame:
        """Read the next normalized spectrum frame."""
