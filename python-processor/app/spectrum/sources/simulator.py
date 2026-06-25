import random
from datetime import datetime, timezone

import numpy as np

from app.config import SpectrumSettings

from .base import SpectrumFrame, SpectrumPoint, SpectrumSource


class SimulatorSpectrumSource(SpectrumSource):
    mode = "simulator"

    def __init__(self, settings: SpectrumSettings):
        self.settings = settings

    def get_status(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "active": True,
            "status": "ok",
            "message": "Simulator spectrum source active",
            "config": self.settings.public_simulator_config(),
        }

    async def read_frame(self) -> SpectrumFrame:
        frequencies = np.linspace(
            self.settings.start_mhz,
            self.settings.end_mhz,
            self.settings.point_count,
        )
        powers = [random.uniform(-95.0, -90.0) for _ in frequencies]

        anomaly_frequency = self.settings.demo_anomaly_frequency_mhz
        if (
            self.settings.demo_anomaly_enabled
            and self.settings.start_mhz <= anomaly_frequency <= self.settings.end_mhz
        ):
            nearest_index = int(np.abs(frequencies - anomaly_frequency).argmin())
            target_level = self.settings.demo_anomaly_level_dbm
            powers[nearest_index] = target_level + random.uniform(-1.0, 1.0)
            for offset in (-2, -1, 1, 2):
                index = nearest_index + offset
                if 0 <= index < len(powers):
                    shoulder_level = target_level - (8.0 * abs(offset)) + random.uniform(-1.5, 1.5)
                    powers[index] = max(powers[index], shoulder_level)

        points = tuple(
            SpectrumPoint(frequency_mhz=float(frequency), power_dbm=float(power))
            for frequency, power in zip(frequencies, powers)
        )
        return SpectrumFrame(
            timestamp=datetime.now(timezone.utc),
            source_mode=self.mode,
            points=points,
        )
