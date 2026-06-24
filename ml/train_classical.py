#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-processor"))

from app.ml.classical import NearestCentroidRfClassifier  # noqa: E402
from app.ml.features import extract_spectrogram_features  # noqa: E402
from app.ml.metrics import classification_metrics  # noqa: E402


def load_manifest(path: Path) -> dict[str, dict]:
    values = {}
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                item = json.loads(line)
                values[str(item["item_id"])] = item
    return values


def partition_features(ids: list[str], manifest: dict[str, dict]) -> tuple[np.ndarray, list[str]]:
    features = []
    labels = []
    for item_id in ids:
        item = manifest[item_id]
        if item.get("label_quality") == "weak_label":
            raise ValueError("weak labels cannot be used by the classical trainer")
        with np.load(item["processed_path"], allow_pickle=False) as sample:
            features.append(extract_spectrogram_features(sample["spectrogram"]))
        labels.append(str(item["label"]))
    if not features:
        raise ValueError("dataset partition is empty")
    return np.stack(features), labels


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and evaluate the classical RF baseline")
    parser.add_argument("manifest_jsonl", type=Path)
    parser.add_argument("split_json", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()

    manifest = load_manifest(args.manifest_jsonl)
    split = json.loads(args.split_json.read_text(encoding="utf-8"))
    partitions = split["partitions"]
    train_ids = list(partitions["train"])
    test_ids = list(partitions["test"])
    if set(train_ids) & set(test_ids):
        raise ValueError("train/test item leakage detected")
    train_x, train_y = partition_features(train_ids, manifest)
    test_x, test_y = partition_features(test_ids, manifest)
    model = NearestCentroidRfClassifier().fit(train_x, train_y)
    started = time.perf_counter()
    predicted = model.predict(test_x)
    inference_ms = (time.perf_counter() - started) * 1000.0 / len(test_y)
    metrics = classification_metrics(test_y, predicted, list(model.classes))

    args.output_directory.mkdir(parents=True, exist_ok=True)
    model_path = args.output_directory / "rf_nearest_centroid_v1.npz"
    np.savez_compressed(
        model_path,
        classes=np.asarray(model.classes),
        centroids=model.centroids,
        feature_mean=model.feature_mean,
        feature_scale=model.feature_scale,
    )
    metrics.update(
        {
            "model_version": "rf_nearest_centroid_v1",
            "model_type": "classical_ml",
            "split_manifest": str(args.split_json),
            "train_samples": len(train_y),
            "test_samples": len(test_y),
            "inference_time_ms_per_sample": round(inference_ms, 6),
            "model_size_bytes": model_path.stat().st_size,
        }
    )
    (args.output_directory / "metrics.json").write_text(
        json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metrics))


if __name__ == "__main__":
    main()
