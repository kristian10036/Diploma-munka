from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class PreparedSpectrogram:
    normalized: np.ndarray
    powers_dbm: np.ndarray
    frequencies_hz: np.ndarray
    source_types: tuple[str, ...]
    session_ids: tuple[str, ...]


class SpectrogramPreprocessor:
    """Builds a fixed-width, robustly normalized spectrogram from SpectrumFrame v1."""

    def __init__(self, frequency_bins: int = 256, time_bins: int = 32) -> None:
        if frequency_bins < 16 or time_bins < 1:
            raise ValueError("frequency_bins must be >=16 and time_bins must be >=1")
        self.frequency_bins = frequency_bins
        self.time_bins = time_bins

    def prepare(self, frames: list[dict[str, Any]]) -> PreparedSpectrogram:
        if not frames:
            raise ValueError("at least one SpectrumFrame is required")
        selected = frames[-self.time_bins :]
        rows: list[np.ndarray] = []
        source_types: list[str] = []
        session_ids: list[str] = []
        common_axis: np.ndarray | None = None

        for frame in selected:
            self._validate_frame(frame)
            count = int(frame["num_points"])
            axis = int(frame["start_frequency_hz"]) + np.arange(count) * int(
                frame["step_frequency_hz"]
            )
            powers = np.asarray(frame["powers_dbm"], dtype=np.float32)
            target = np.linspace(axis[0], axis[-1], self.frequency_bins)
            rows.append(np.interp(target, axis, powers).astype(np.float32))
            if common_axis is None:
                common_axis = target
            elif not np.allclose(common_axis, target, rtol=0, atol=1):
                raise ValueError("all frames must cover the same frequency range")
            source_types.append(str(frame["source_type"]))
            session_ids.append(str(frame["session_id"]))

        powers_dbm = np.stack(rows)
        median = np.median(powers_dbm, axis=1, keepdims=True)
        mad = np.median(np.abs(powers_dbm - median), axis=1, keepdims=True)
        scale = np.maximum(mad * 1.4826, 1.0)
        normalized = np.clip((powers_dbm - median) / scale, -6.0, 12.0) / 12.0
        return PreparedSpectrogram(
            normalized=normalized.astype(np.float32),
            powers_dbm=powers_dbm,
            frequencies_hz=np.asarray(common_axis, dtype=np.float64),
            source_types=tuple(source_types),
            session_ids=tuple(session_ids),
        )

    @staticmethod
    def _validate_frame(frame: dict[str, Any]) -> None:
        required = {
            "schema_version",
            "source_type",
            "session_id",
            "start_frequency_hz",
            "stop_frequency_hz",
            "step_frequency_hz",
            "num_points",
            "power_unit",
            "powers_dbm",
        }
        if not isinstance(frame, dict) or not required <= frame.keys():
            raise ValueError("missing SpectrumFrame fields")
        if frame["schema_version"] != 1 or frame["power_unit"] != "dBm":
            raise ValueError("unsupported SpectrumFrame schema or power unit")
        if frame["source_type"] not in {"mock", "replay", "aaronia", "usrp", "hackrf"}:
            raise ValueError("invalid source_type")
        count = frame["num_points"]
        step = frame["step_frequency_hz"]
        if not isinstance(count, int) or isinstance(count, bool) or count < 2 or count > 65536:
            raise ValueError("invalid num_points")
        if not isinstance(step, int) or isinstance(step, bool) or step <= 0:
            raise ValueError("invalid step_frequency_hz")
        expected_stop = frame["start_frequency_hz"] + step * (count - 1)
        if frame["stop_frequency_hz"] != expected_stop:
            raise ValueError("inconsistent frequency axis")
        powers = frame["powers_dbm"]
        if not isinstance(powers, list) or len(powers) != count:
            raise ValueError("powers_dbm length mismatch")
        values = np.asarray(powers, dtype=np.float64)
        if not np.isfinite(values).all():
            raise ValueError("powers_dbm contains non-finite values")
