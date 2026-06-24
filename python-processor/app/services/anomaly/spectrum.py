from __future__ import annotations

import math
import os
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

import numpy as np


@dataclass(frozen=True, slots=True)
class Detection:
    entity_domain: str
    class_name: str
    severity: str
    confidence: float | None
    explanation: str
    start_frequency_hz: int | None = None
    stop_frequency_hz: int | None = None
    center_frequency_hz: int | None = None
    power_dbm: float | None = None
    bandwidth_hz: int | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    detected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    detector_name: str = "robust_spectrum_baseline"
    detector_version: str = "1.0.0"

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_domain": self.entity_domain,
            "class_name": self.class_name,
            "severity": self.severity,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "start_frequency_hz": self.start_frequency_hz,
            "stop_frequency_hz": self.stop_frequency_hz,
            "center_frequency_hz": self.center_frequency_hz,
            "power_dbm": self.power_dbm,
            "bandwidth_hz": self.bandwidth_hz,
            "evidence": self.evidence,
            "detected_at": self.detected_at,
            "detector_name": self.detector_name,
            "detector_version": self.detector_version,
        }


@dataclass(frozen=True, slots=True)
class SpectrumAnomalyConfig:
    history_frames: int = 24
    warmup_frames: int = 6
    peak_delta_db: float = 8.0
    robust_sigma_multiplier: float = 6.0
    noise_floor_shift_db: float = 5.0
    occupancy_change_fraction: float = 0.12
    narrowband_max_hz: int = 200_000
    persistence_frames: int = 3
    bandwidth_ratio_change: float = 2.5
    cooldown_frames: int = 10

    @classmethod
    def from_env(cls) -> "SpectrumAnomalyConfig":
        def integer(name: str, default: int, low: int, high: int) -> int:
            try:
                return max(low, min(high, int(os.getenv(name, str(default)))))
            except ValueError:
                return default

        def number(name: str, default: float, low: float, high: float) -> float:
            try:
                return max(low, min(high, float(os.getenv(name, str(default)))))
            except ValueError:
                return default

        return cls(
            history_frames=integer("ANOMALY_HISTORY_FRAMES", 24, 6, 512),
            warmup_frames=integer("ANOMALY_WARMUP_FRAMES", 6, 3, 128),
            peak_delta_db=number("ANOMALY_PEAK_DELTA_DB", 8.0, 1.0, 60.0),
            robust_sigma_multiplier=number("ANOMALY_MAD_MULTIPLIER", 6.0, 1.0, 30.0),
            noise_floor_shift_db=number("ANOMALY_NOISE_SHIFT_DB", 5.0, 1.0, 40.0),
            occupancy_change_fraction=number("ANOMALY_OCCUPANCY_CHANGE", 0.12, 0.01, 1.0),
            narrowband_max_hz=integer("ANOMALY_NARROWBAND_MAX_HZ", 200_000, 1_000, 100_000_000),
            persistence_frames=integer("ANOMALY_PERSISTENCE_FRAMES", 3, 2, 30),
            bandwidth_ratio_change=number("ANOMALY_BANDWIDTH_RATIO_CHANGE", 2.5, 1.1, 20.0),
            cooldown_frames=integer("ANOMALY_COOLDOWN_FRAMES", 10, 1, 1000),
        )


class SpectrumAnomalyDetector:
    """Transparent rolling median/MAD detector; no trained model is implied."""

    def __init__(self, config: SpectrumAnomalyConfig | None = None):
        self.config = config or SpectrumAnomalyConfig.from_env()
        self._powers: deque[np.ndarray] = deque(maxlen=self.config.history_frames)
        self._frequencies: np.ndarray | None = None
        self._last_sequence: int | None = None
        self._last_dominant_hz: int | None = None
        self._last_bandwidth_hz: int | None = None
        self._dominant_history: deque[int] = deque(maxlen=self.config.persistence_frames)
        self._cooldowns: Counter[str] = Counter()
        self.frames_processed = 0

    @staticmethod
    def _validate(frequencies_hz: Sequence[int | float], powers_dbm: Sequence[int | float]) -> tuple[np.ndarray, np.ndarray]:
        frequencies = np.asarray(frequencies_hz, dtype=np.float64)
        powers = np.asarray(powers_dbm, dtype=np.float64)
        if frequencies.ndim != 1 or powers.ndim != 1 or len(frequencies) != len(powers) or len(powers) < 2:
            raise ValueError("invalid_spectrum_shape")
        if not np.isfinite(frequencies).all() or not np.isfinite(powers).all():
            raise ValueError("non_finite_spectrum")
        if np.any(np.diff(frequencies) <= 0) or frequencies[0] < 0:
            raise ValueError("non_monotonic_frequency_axis")
        return frequencies, powers

    @staticmethod
    def _groups(mask: np.ndarray) -> list[tuple[int, int]]:
        groups: list[tuple[int, int]] = []
        start: int | None = None
        for index, active in enumerate(mask):
            if active and start is None:
                start = index
            elif not active and start is not None:
                groups.append((start, index - 1))
                start = None
        if start is not None:
            groups.append((start, len(mask) - 1))
        return groups

    def _emit_once(self, key: str) -> bool:
        remaining = self._cooldowns.get(key, 0)
        if remaining > 0:
            return False
        self._cooldowns[key] = self.config.cooldown_frames
        return True

    def process(
        self,
        frequencies_hz: Sequence[int | float],
        powers_dbm: Sequence[int | float],
        *,
        sequence: int | None = None,
        source_type: str | None = None,
        timestamp: str | None = None,
        reference_powers_dbm: Sequence[int | float] | None = None,
    ) -> list[Detection]:
        frequencies, powers = self._validate(frequencies_hz, powers_dbm)
        self.frames_processed += 1
        for key in list(self._cooldowns):
            self._cooldowns[key] -= 1
            if self._cooldowns[key] <= 0:
                del self._cooldowns[key]
        detections: list[Detection] = []
        detected_at = timestamp or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        if sequence is not None:
            if self._last_sequence is not None and sequence > self._last_sequence + 1:
                gap = sequence - self._last_sequence - 1
                detections.append(Detection(
                    entity_domain="technical", class_name="sequence_gap", severity="medium",
                    confidence=1.0, explanation=f"A forrásból {gap} spektrumframe hiányzik.",
                    evidence={"previous_sequence": self._last_sequence, "sequence": sequence, "gap": gap,
                              "source_type": source_type}, detected_at=detected_at,
                ))
            self._last_sequence = sequence

        if self._frequencies is None or len(self._frequencies) != len(frequencies) or not np.allclose(self._frequencies, frequencies):
            self._powers.clear()
            self._dominant_history.clear()
            self._last_dominant_hz = None
            self._last_bandwidth_hz = None
            self._frequencies = frequencies.copy()

        if reference_powers_dbm is not None:
            reference = np.asarray(reference_powers_dbm, dtype=np.float64)
            if reference.shape != powers.shape or not np.isfinite(reference).all():
                raise ValueError("invalid_reference_shape")
            baseline = reference
            robust_sigma = np.full_like(powers, 0.5)
            baseline_source = "versioned_reference"
        elif len(self._powers) >= self.config.warmup_frames:
            history = np.stack(tuple(self._powers), axis=0)
            baseline = np.median(history, axis=0)
            mad = np.median(np.abs(history - baseline), axis=0)
            robust_sigma = np.maximum(1.4826 * mad, 0.5)
            baseline_source = "rolling_median_mad"
        else:
            self._powers.append(powers.copy())
            return detections

        threshold = baseline + np.maximum(
            self.config.peak_delta_db,
            self.config.robust_sigma_multiplier * robust_sigma,
        )
        new_mask = powers > threshold
        groups = sorted(
            self._groups(new_mask),
            key=lambda group: float(np.max(powers[group[0]:group[1] + 1] - baseline[group[0]:group[1] + 1])),
            reverse=True,
        )
        bin_hz = float(np.median(np.diff(frequencies)))
        current_floor = float(np.median(powers))
        baseline_floor = float(np.median(baseline))
        occupancy_threshold = current_floor + self.config.peak_delta_db
        current_occupancy = float(np.mean(powers > occupancy_threshold))
        baseline_occupancy = float(np.mean(baseline > baseline_floor + self.config.peak_delta_db))

        if abs(current_floor - baseline_floor) >= self.config.noise_floor_shift_db and self._emit_once("noise_floor_shift"):
            detections.append(Detection(
                entity_domain="spectrum", class_name="noise_floor_shift", severity="medium",
                confidence=min(0.99, 0.65 + abs(current_floor - baseline_floor) / 40.0),
                explanation="A teljes sáv robusztus zajpadlója jelentősen eltért a baseline-tól.",
                start_frequency_hz=int(frequencies[0]), stop_frequency_hz=int(frequencies[-1]),
                evidence={"current_median_dbm": current_floor, "baseline_median_dbm": baseline_floor,
                          "delta_db": current_floor - baseline_floor, "baseline_source": baseline_source},
                detected_at=detected_at,
            ))

        occupancy_delta = current_occupancy - baseline_occupancy
        if abs(occupancy_delta) >= self.config.occupancy_change_fraction and self._emit_once("occupancy_change"):
            detections.append(Detection(
                entity_domain="spectrum", class_name="occupancy_change", severity="medium",
                confidence=min(0.98, 0.60 + abs(occupancy_delta)),
                explanation="A foglalt spektrumbinek aránya lényegesen megváltozott.",
                start_frequency_hz=int(frequencies[0]), stop_frequency_hz=int(frequencies[-1]),
                evidence={"current_occupancy": current_occupancy, "baseline_occupancy": baseline_occupancy,
                          "delta": occupancy_delta, "baseline_source": baseline_source}, detected_at=detected_at,
            ))

        for start, stop in groups[:5]:
            segment_delta = powers[start:stop + 1] - baseline[start:stop + 1]
            peak_relative = int(np.argmax(segment_delta))
            peak_index = start + peak_relative
            bandwidth = max(int(round((stop - start + 1) * bin_hz)), int(round(bin_hz)))
            center = int(round(frequencies[peak_index]))
            delta_db = float(segment_delta[peak_relative])
            severity = "high" if delta_db >= 20 else "medium"
            key = f"new_peak:{round(center / max(bin_hz, 1))}"
            if self._emit_once(key):
                detections.append(Detection(
                    entity_domain="spectrum", class_name="new_peak_above_reference", severity=severity,
                    confidence=min(0.995, 0.65 + delta_db / 60.0),
                    explanation="Új spektrumcsúcs jelent meg a robusztus baseline felett.",
                    start_frequency_hz=int(round(frequencies[start])),
                    stop_frequency_hz=int(round(frequencies[stop])), center_frequency_hz=center,
                    power_dbm=float(powers[peak_index]), bandwidth_hz=bandwidth,
                    evidence={"delta_db": delta_db, "baseline_dbm": float(baseline[peak_index]),
                              "robust_sigma_db": float(robust_sigma[peak_index]),
                              "baseline_source": baseline_source, "source_type": source_type},
                    detected_at=detected_at,
                ))

        dominant_index = int(np.argmax(powers))
        dominant_hz = int(round(frequencies[dominant_index]))
        dominant_power = float(powers[dominant_index])
        active = powers > current_floor + self.config.peak_delta_db
        active_groups = self._groups(active)
        dominant_group = next((group for group in active_groups if group[0] <= dominant_index <= group[1]), (dominant_index, dominant_index))
        dominant_bandwidth = max(
            int(round((dominant_group[1] - dominant_group[0] + 1) * bin_hz)), int(round(bin_hz))
        )
        signal_present = dominant_power - current_floor >= self.config.peak_delta_db
        if signal_present:
            bucket = int(round(dominant_hz / max(bin_hz, 1)))
            self._dominant_history.append(bucket)
            if (
                dominant_bandwidth <= self.config.narrowband_max_hz
                and len(self._dominant_history) == self.config.persistence_frames
                and len(set(self._dominant_history)) == 1
                and self._emit_once(f"persistent:{bucket}")
            ):
                detections.append(Detection(
                    entity_domain="spectrum", class_name="persistent_narrowband", severity="medium",
                    confidence=0.86, explanation="Keskenysávú csúcs több egymást követő frame-ben fennmaradt.",
                    center_frequency_hz=dominant_hz, power_dbm=dominant_power,
                    bandwidth_hz=dominant_bandwidth,
                    start_frequency_hz=int(round(frequencies[dominant_group[0]])),
                    stop_frequency_hz=int(round(frequencies[dominant_group[1]])),
                    evidence={"persistence_frames": self.config.persistence_frames,
                              "noise_floor_dbm": current_floor}, detected_at=detected_at,
                ))
            if self._last_bandwidth_hz and min(self._last_bandwidth_hz, dominant_bandwidth) > 0:
                ratio = max(self._last_bandwidth_hz, dominant_bandwidth) / min(self._last_bandwidth_hz, dominant_bandwidth)
                if ratio >= self.config.bandwidth_ratio_change and self._emit_once("bandwidth_change"):
                    detections.append(Detection(
                        entity_domain="spectrum", class_name="unexpected_bandwidth_change", severity="medium",
                        confidence=min(0.98, 0.62 + ratio / 20.0),
                        explanation="A domináns jel becsült sávszélessége hirtelen megváltozott.",
                        center_frequency_hz=dominant_hz, power_dbm=dominant_power,
                        bandwidth_hz=dominant_bandwidth,
                        evidence={"previous_bandwidth_hz": self._last_bandwidth_hz,
                                  "current_bandwidth_hz": dominant_bandwidth, "ratio": ratio},
                        detected_at=detected_at,
                    ))
            if self._last_dominant_hz is not None:
                drift = abs(dominant_hz - self._last_dominant_hz)
                if drift >= max(int(round(3 * bin_hz)), self.config.narrowband_max_hz) and self._emit_once("frequency_drift"):
                    detections.append(Detection(
                        entity_domain="spectrum", class_name="frequency_drift", severity="low",
                        confidence=0.74, explanation="A domináns keskenysávú energia más frekvenciára vándorolt.",
                        center_frequency_hz=dominant_hz, power_dbm=dominant_power,
                        bandwidth_hz=dominant_bandwidth,
                        evidence={"previous_frequency_hz": self._last_dominant_hz,
                                  "current_frequency_hz": dominant_hz, "drift_hz": drift}, detected_at=detected_at,
                    ))
        else:
            self._dominant_history.clear()

        if groups and self._powers:
            previous = self._powers[-1]
            previous_delta = powers - previous
            max_delta_index = int(np.argmax(previous_delta))
            if previous_delta[max_delta_index] >= self.config.peak_delta_db * 1.5 and self._emit_once("burst"):
                detections.append(Detection(
                    entity_domain="spectrum", class_name="short_burst", severity="medium",
                    confidence=min(0.95, 0.65 + float(previous_delta[max_delta_index]) / 60.0),
                    explanation="Rövid, az előző frame-ben nem jelen lévő energialöket jelent meg.",
                    center_frequency_hz=int(round(frequencies[max_delta_index])),
                    power_dbm=float(powers[max_delta_index]), bandwidth_hz=int(round(bin_hz)),
                    evidence={"frame_to_frame_delta_db": float(previous_delta[max_delta_index])},
                    detected_at=detected_at,
                ))

        self._last_dominant_hz = dominant_hz if signal_present else None
        self._last_bandwidth_hz = dominant_bandwidth if signal_present else None
        self._powers.append(powers.copy())
        return detections

    def status(self) -> dict[str, Any]:
        return {
            "implemented": True,
            "status": "ready" if len(self._powers) >= self.config.warmup_frames else "warming_up",
            "detector_name": "robust_spectrum_baseline",
            "detector_version": "1.0.0",
            "history_frames": len(self._powers),
            "warmup_frames": self.config.warmup_frames,
            "frames_processed": self.frames_processed,
            "trained_model_required": False,
        }
