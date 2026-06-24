import asyncio
import json
from datetime import datetime
from typing import Any

import websockets

from app.config import SpectrumSettings

from .base import SpectrumFrame, SpectrumPoint, SpectrumSource, SpectrumSourceUnavailable


class SpectrumIngestWebSocketSource(SpectrumSource):
    """Consumes validated SpectrumFrame v1 messages from spectrum-ingest."""

    mode = "spectrum_ingest"

    def __init__(self, settings: SpectrumSettings):
        self.settings = settings
        self._socket: Any = None
        self._last_error: str | None = None
        self._last_frame_at: str | None = None
        self._last_frame_metadata: dict[str, Any] | None = None

    def get_status(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "active": self._socket is not None,
            "status": "ok" if self._socket is not None else "degraded",
            "message": self._last_error or "Spectrum ingest WebSocket configured",
            "last_frame_at": self._last_frame_at,
            "last_frame": self._last_frame_metadata,
        }

    async def _disconnect(self) -> None:
        socket, self._socket = self._socket, None
        if socket is not None:
            try:
                await socket.close()
            except Exception:
                pass

    async def read_frame(self) -> SpectrumFrame:
        try:
            if self._socket is None:
                self._socket = await websockets.connect(
                    self.settings.spectrum_ingest_ws_url,
                    open_timeout=self.settings.spectrum_ingest_timeout_seconds,
                    close_timeout=2,
                    max_size=4 * 1024 * 1024,
                )
            payload = await asyncio.wait_for(
                self._socket.recv(), timeout=self.settings.spectrum_ingest_timeout_seconds
            )
            frame = self._parse_frame(payload)
            self._last_error = None
            self._last_frame_at = frame.timestamp.isoformat()
            self._last_frame_metadata = {
                "device_model": frame.device_model,
                "measurement_mode": frame.measurement_mode,
                "start_frequency_hz": int(frame.points[0].frequency_mhz * 1_000_000),
                "stop_frequency_hz": int(frame.points[-1].frequency_mhz * 1_000_000),
                "point_count": len(frame.points),
            }
            return frame
        except asyncio.CancelledError:
            await self._disconnect()
            raise
        except Exception as exc:
            await self._disconnect()
            self._last_error = f"{type(exc).__name__}: {exc}"
            raise SpectrumSourceUnavailable(
                f"Spectrum ingest unavailable: {self._last_error}"
            ) from exc

    @staticmethod
    def _parse_frame(payload: str | bytes) -> SpectrumFrame:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        value = json.loads(payload)
        required = (
            "schema_version", "source_type", "source_device", "device_model", "measurement_mode", "timestamp", "sequence",
            "start_frequency_hz", "step_frequency_hz", "num_points", "point_count", "powers_dbm", "flags",
        )
        if not isinstance(value, dict) or any(field not in value for field in required):
            raise ValueError("invalid SpectrumFrame fields")
        powers = value["powers_dbm"]
        count = value["num_points"]
        if value["schema_version"] != 1 or value["point_count"] != count or not isinstance(powers, list) or count != len(powers):
            raise ValueError("invalid SpectrumFrame shape")
        if count < 2 or count > 65_536 or not all(isinstance(power, (int, float)) for power in powers):
            raise ValueError("invalid SpectrumFrame powers")
        start = int(value["start_frequency_hz"])
        step = int(value["step_frequency_hz"])
        if start < 0 or step <= 0 or not isinstance(value["sequence"], int) or value["sequence"] < 0:
            raise ValueError("invalid SpectrumFrame frequency or sequence")
        timestamp = datetime.fromisoformat(str(value["timestamp"]).replace("Z", "+00:00"))
        points = tuple(
            SpectrumPoint((start + index * step) / 1_000_000.0, float(power))
            for index, power in enumerate(powers)
        )
        return SpectrumFrame(
            timestamp=timestamp,
            source_mode=str(value["source_type"]),
            points=points,
            sequence=value["sequence"],
            source_device=str(value["source_device"]),
            device_model=str(value["device_model"]),
            measurement_mode=str(value["measurement_mode"]),
            flags=dict(value["flags"]),
        )
