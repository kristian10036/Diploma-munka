#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-processor"))

from app.ml.cnn import build_small_cnn  # noqa: E402
from app.ml.metrics import classification_metrics  # noqa: E402


def load_manifest(path: Path) -> dict[str, dict]:
    result = {}
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                item = json.loads(line)
                result[str(item["item_id"])] = item
    return result


def load_partition(ids: list[str], manifest: dict[str, dict], class_index: dict[str, int]):
    import torch

    samples = []
    labels = []
    for item_id in ids:
        item = manifest[item_id]
        if item.get("label_quality") == "weak_label":
            raise ValueError("weak labels cannot be used by the CNN trainer")
        label = str(item["label"])
        if label not in class_index:
            raise ValueError(f"partition contains unseen class: {label}")
        with np.load(item["processed_path"], allow_pickle=False) as sample:
            spectrogram = np.asarray(sample["spectrogram"], dtype=np.float32)
        if spectrogram.ndim != 2 or not np.isfinite(spectrogram).all():
            raise ValueError("invalid processed spectrogram")
        samples.append(spectrogram[None, :, :])
        labels.append(class_index[label])
    if not samples:
        raise ValueError("dataset partition is empty")
    return torch.from_numpy(np.stack(samples)), torch.tensor(labels, dtype=torch.long)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the small CPU RF CNN")
    parser.add_argument("manifest_jsonl", type=Path)
    parser.add_argument("split_json", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=20260619)
    args = parser.parse_args()
    if args.epochs < 1 or args.batch_size < 1 or args.learning_rate <= 0:
        raise ValueError("invalid training hyperparameters")

    try:
        import torch
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError as exc:
        raise RuntimeError("install ml/requirements-training.txt for CNN training") from exc

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(max(1, min(4, torch.get_num_threads())))

    manifest = load_manifest(args.manifest_jsonl)
    split = json.loads(args.split_json.read_text(encoding="utf-8"))["partitions"]
    train_ids, validation_ids, test_ids = map(list, (split["train"], split["validation"], split["test"]))
    if (set(train_ids) & set(validation_ids)) or (set(train_ids) & set(test_ids)) or (set(validation_ids) & set(test_ids)):
        raise ValueError("dataset item leakage detected")
    classes = sorted({str(manifest[item_id]["label"]) for item_id in train_ids})
    if len(classes) < 2:
        raise ValueError("CNN training requires at least two training classes")
    class_index = {label: index for index, label in enumerate(classes)}
    train_x, train_y = load_partition(train_ids, manifest, class_index)
    validation_x, validation_y = load_partition(validation_ids, manifest, class_index)
    test_x, test_y = load_partition(test_ids, manifest, class_index)

    model = build_small_cnn(len(classes)).cpu()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)
    criterion = torch.nn.CrossEntropyLoss()
    generator = torch.Generator().manual_seed(args.seed)
    loader = DataLoader(TensorDataset(train_x, train_y), batch_size=args.batch_size, shuffle=True, generator=generator)
    history = []
    for epoch in range(args.epochs):
        model.train()
        losses = []
        for batch_x, batch_y in loader:
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(batch_x), batch_y)
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach()))
        model.eval()
        with torch.inference_mode():
            validation_loss = float(criterion(model(validation_x), validation_y))
        history.append({"epoch": epoch + 1, "train_loss": float(np.mean(losses)), "validation_loss": validation_loss})

    model.eval()
    started = time.perf_counter()
    with torch.inference_mode():
        predicted_indices = model(test_x).argmax(dim=1).tolist()
    inference_ms = (time.perf_counter() - started) * 1000.0 / len(test_y)
    expected = [classes[index] for index in test_y.tolist()]
    predicted = [classes[index] for index in predicted_indices]
    metrics = classification_metrics(expected, predicted, classes)

    args.output_directory.mkdir(parents=True, exist_ok=True)
    model_path = args.output_directory / "rf_small_cnn_v1.pt"
    torch.save({"state_dict": model.state_dict(), "classes": classes}, model_path)
    metrics.update(
        {
            "model_version": "rf_small_cnn_v1",
            "model_type": "cnn",
            "classes": classes,
            "epochs": args.epochs,
            "seed": args.seed,
            "train_samples": len(train_y),
            "validation_samples": len(validation_y),
            "test_samples": len(test_y),
            "inference_time_ms_per_sample": round(inference_ms, 6),
            "model_size_bytes": model_path.stat().st_size,
            "history": history,
        }
    )
    (args.output_directory / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics))


if __name__ == "__main__":
    main()
