from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class NearestCentroidRfClassifier:
    """Small deterministic classical-ML baseline for extracted spectrum features."""

    classes: tuple[str, ...] = ()
    centroids: np.ndarray | None = None
    feature_mean: np.ndarray | None = None
    feature_scale: np.ndarray | None = None

    def fit(self, features: np.ndarray, labels: list[str]) -> "NearestCentroidRfClassifier":
        values = np.asarray(features, dtype=np.float64)
        if values.ndim != 2 or values.shape[0] != len(labels) or values.shape[0] < 2:
            raise ValueError("features and labels must contain at least two aligned samples")
        if not np.isfinite(values).all():
            raise ValueError("features contain non-finite values")
        self.feature_mean = values.mean(axis=0)
        self.feature_scale = np.maximum(values.std(axis=0), 1e-9)
        normalized = (values - self.feature_mean) / self.feature_scale
        self.classes = tuple(sorted(set(labels)))
        if len(self.classes) < 2:
            raise ValueError("at least two classes are required")
        self.centroids = np.stack(
            [normalized[np.asarray(labels) == label].mean(axis=0) for label in self.classes]
        )
        return self

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        if self.centroids is None or self.feature_mean is None or self.feature_scale is None:
            raise RuntimeError("classifier is not fitted")
        values = np.atleast_2d(np.asarray(features, dtype=np.float64))
        normalized = (values - self.feature_mean) / self.feature_scale
        distances = np.linalg.norm(normalized[:, None, :] - self.centroids[None, :, :], axis=2)
        scores = np.exp(-(distances - distances.min(axis=1, keepdims=True)))
        return scores / scores.sum(axis=1, keepdims=True)

    def predict(self, features: np.ndarray) -> list[str]:
        probabilities = self.predict_proba(features)
        return [self.classes[index] for index in probabilities.argmax(axis=1)]
