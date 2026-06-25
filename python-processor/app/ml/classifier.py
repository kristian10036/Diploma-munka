from __future__ import annotations

import math
import time
from typing import Any

import numpy as np

from .preprocessing import SpectrogramPreprocessor

RF_CLASSES = (
    "wifi_2_4g",
    "wifi_5g",
    "bluetooth",
    "zigbee",
    "narrowband_unknown",
    "wideband_unknown",
    "noise",
    "unknown",
)


class RuleBasedRfClassifier:
    """Transparent CPU baseline; it does not claim classes lacking separable evidence."""

    model_version = "rf_rule_baseline_v1"
    model_type = "rule_based_baseline"

    def __init__(self) -> None:
        self.preprocessor = SpectrogramPreprocessor()

    def classify(self, frames: list[dict[str, Any]]) -> dict[str, Any]:
        started = time.perf_counter()
        prepared = self.preprocessor.prepare(frames)
        powers = prepared.powers_dbm
        median = np.median(powers, axis=1)
        peaks = np.max(powers, axis=1)
        peak_delta = float(np.median(peaks - median))
        threshold = median[:, None] + 6.0
        occupied_fraction = float(np.mean(powers > threshold))
        peak_bins = np.argmax(powers, axis=1)
        hopping_fraction = float(np.std(peak_bins) / max(1, powers.shape[1] - 1))
        center_hz = float(np.mean(prepared.frequencies_hz))
        span_hz = float(prepared.frequencies_hz[-1] - prepared.frequencies_hz[0])

        predicted, confidence, reason = self._decision(
            center_hz, span_hz, peak_delta, occupied_fraction, hopping_fraction
        )
        alternatives = self._alternatives(predicted, confidence)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return {
            "model_version": self.model_version,
            "model_type": self.model_type,
            "predicted_class": predicted,
            "confidence": round(confidence, 4),
            "top_predictions": alternatives,
            "inference_time_ms": round(elapsed_ms, 3),
            "features": {
                "center_frequency_hz": round(center_hz),
                "span_hz": round(span_hz),
                "peak_above_median_db": round(peak_delta, 3),
                "occupied_fraction": round(occupied_fraction, 5),
                "peak_hopping_fraction": round(hopping_fraction, 5),
                "time_bins": int(powers.shape[0]),
                "frequency_bins": int(powers.shape[1]),
            },
            "explanation": reason,
        }

    @staticmethod
    def _decision(
        center_hz: float,
        span_hz: float,
        peak_delta: float,
        occupied: float,
        hopping: float,
    ) -> tuple[str, float, str]:
        in_24g = 2.4e9 <= center_hz <= 2.5e9
        in_5g = 5.15e9 <= center_hz <= 5.9e9
        if peak_delta < 6.0:
            return (
                "noise",
                min(0.92, 0.60 + (6.0 - peak_delta) / 20.0),
                "no peak exceeds the robust noise floor by 6 dB",
            )
        if in_24g and occupied < 0.08 and hopping > 0.08:
            return (
                "bluetooth",
                min(0.88, 0.62 + hopping),
                "narrow hopping peaks in the 2.4 GHz ISM band",
            )
        if in_24g and occupied >= 0.08 and span_hz >= 15e6:
            return (
                "wifi_2_4g",
                min(0.90, 0.65 + occupied / 2.0),
                "wide occupied spectrum in the 2.4 GHz Wi-Fi band",
            )
        if in_5g and occupied >= 0.08 and span_hz >= 15e6:
            return (
                "wifi_5g",
                min(0.90, 0.65 + occupied / 2.0),
                "wide occupied spectrum in the 5 GHz Wi-Fi band",
            )
        if occupied < 0.08:
            return (
                "narrowband_unknown",
                min(0.86, 0.64 + peak_delta / 100.0),
                "strong signal with narrow occupied bandwidth",
            )
        if occupied >= 0.30:
            return (
                "wideband_unknown",
                min(0.86, 0.62 + occupied / 3.0),
                "broad occupied bandwidth without enough protocol evidence",
            )
        return "unknown", 0.51, "signal evidence is insufficient for a supported baseline class"

    @staticmethod
    def _alternatives(predicted: str, confidence: float) -> list[dict[str, Any]]:
        residual = max(0.0, 1.0 - confidence)
        fallback = "unknown" if predicted != "unknown" else "noise"
        values = [(predicted, confidence), (fallback, residual)]
        return [
            {"class": name, "confidence": round(value, 4)}
            for name, value in values
            if math.isfinite(value) and value > 0
        ]

    def status(self) -> dict[str, Any]:
        return {
            "available": True,
            "status": "baseline_loaded",
            "model_version": self.model_version,
            "model_type": self.model_type,
            "device": "cpu",
            "supported_classes": [
                "wifi_2_4g",
                "wifi_5g",
                "bluetooth",
                "narrowband_unknown",
                "wideband_unknown",
                "noise",
                "unknown",
            ],
            "withheld_classes": ["zigbee"],
        }
