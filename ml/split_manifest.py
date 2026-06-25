#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-processor"))

from app.ml.dataset import DatasetItem, grouped_split  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Create leakage-safe RF dataset splits")
    parser.add_argument("labels_jsonl", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--seed", default="rf-dataset-v1")
    args = parser.parse_args()

    items: list[DatasetItem] = []
    with args.labels_jsonl.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            try:
                items.append(
                    DatasetItem(
                        item_id=str(value["item_id"]),
                        recording_id=str(value.get("recording_id", "")),
                        session_id=str(value.get("session_id", "")),
                        label=str(value["label"]),
                    )
                )
            except (KeyError, TypeError) as exc:
                raise ValueError(f"invalid label at line {line_number}") from exc
    split = grouped_split(items, seed=args.seed)
    output = {
        "schema_version": 1,
        "seed": args.seed,
        "split_unit": "recording_or_session",
        "partitions": {name: [item.item_id for item in values] for name, values in split.items()},
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
