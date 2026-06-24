from __future__ import annotations

from typing import Any

import numpy as np


def classification_metrics(
    expected: list[str], predicted: list[str], classes: list[str] | None = None
) -> dict[str, Any]:
    if not expected or len(expected) != len(predicted):
        raise ValueError("expected and predicted must be non-empty and aligned")
    labels = classes or sorted(set(expected) | set(predicted))
    if len(labels) != len(set(labels)) or not labels:
        raise ValueError("classes must be unique and non-empty")
    index = {label: position for position, label in enumerate(labels)}
    if any(value not in index for value in expected + predicted):
        raise ValueError("sample label is absent from classes")
    matrix = np.zeros((len(labels), len(labels)), dtype=np.int64)
    for actual, guessed in zip(expected, predicted):
        matrix[index[actual], index[guessed]] += 1

    per_class: dict[str, dict[str, float | int]] = {}
    precisions: list[float] = []
    recalls: list[float] = []
    f1_values: list[float] = []
    for position, label in enumerate(labels):
        true_positive = int(matrix[position, position])
        false_positive = int(matrix[:, position].sum() - true_positive)
        false_negative = int(matrix[position, :].sum() - true_positive)
        precision = true_positive / max(1, true_positive + false_positive)
        recall = true_positive / max(1, true_positive + false_negative)
        f1 = 2 * precision * recall / max(1e-12, precision + recall)
        precisions.append(precision)
        recalls.append(recall)
        f1_values.append(f1)
        per_class[label] = {
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "f1": round(f1, 6),
            "support": int(matrix[position, :].sum()),
        }
    return {
        "accuracy": round(float(np.trace(matrix) / matrix.sum()), 6),
        "macro_precision": round(float(np.mean(precisions)), 6),
        "macro_recall": round(float(np.mean(recalls)), 6),
        "macro_f1": round(float(np.mean(f1_values)), 6),
        "per_class": per_class,
        "confusion_matrix": matrix.tolist(),
        "classes": labels,
    }
