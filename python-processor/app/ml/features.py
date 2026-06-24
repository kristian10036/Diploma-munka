from __future__ import annotations

import numpy as np


def extract_spectrogram_features(spectrogram: np.ndarray) -> np.ndarray:
    """Compact, deterministic features for the classical CPU baseline."""
    values = np.asarray(spectrogram, dtype=np.float64)
    if values.ndim != 2 or min(values.shape) < 1 or not np.isfinite(values).all():
        raise ValueError("spectrogram must be a finite two-dimensional array")
    peak_bins = np.argmax(values, axis=1) / max(1, values.shape[1] - 1)
    temporal_peaks = np.max(values, axis=1)
    base = np.asarray(
        [
            values.mean(),
            values.std(),
            values.min(),
            values.max(),
            np.mean(values > 0.5),
            temporal_peaks.mean(),
            temporal_peaks.std(),
            peak_bins.mean(),
            peak_bins.std(),
        ],
        dtype=np.float64,
    )
    frequency_profile = values.mean(axis=0)
    frequency_chunks = np.array_split(frequency_profile, min(16, values.shape[1]))
    pooled_frequency = np.asarray([chunk.mean() for chunk in frequency_chunks])
    time_profile = values.mean(axis=1)
    time_chunks = np.array_split(time_profile, min(8, values.shape[0]))
    pooled_time = np.asarray([chunk.mean() for chunk in time_chunks])
    return np.concatenate((base, pooled_frequency, pooled_time))
