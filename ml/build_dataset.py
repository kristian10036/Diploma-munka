#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-processor"))

from app.ml.recording_dataset import RecordingLabel, build_recording_windows  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build RF spectrogram windows from recordings")
    parser.add_argument("labels_jsonl", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("manifest_jsonl", type=Path)
    parser.add_argument("--time-bins", type=int, default=32)
    parser.add_argument("--frequency-bins", type=int, default=256)
    parser.add_argument("--stride", type=int, default=16)
    parser.add_argument("--allow-weak-labels", action="store_true")
    args = parser.parse_args()

    entries = []
    with args.labels_jsonl.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            try:
                recording = RecordingLabel(
                    recording_path=Path(value["recording_path"]),
                    label=str(value["label"]),
                    label_quality=str(value["label_quality"]),
                    provenance=str(value["provenance"]),
                )
            except (KeyError, TypeError) as exc:
                raise ValueError(f"invalid recording label at line {line_number}") from exc
            entries.extend(
                build_recording_windows(
                    recording,
                    args.output_directory,
                    time_bins=args.time_bins,
                    frequency_bins=args.frequency_bins,
                    stride=args.stride,
                    allow_weak_labels=args.allow_weak_labels,
                )
            )
    args.manifest_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.manifest_jsonl.open("w", encoding="utf-8") as target:
        for entry in entries:
            target.write(json.dumps(entry, sort_keys=True) + "\n")
    print(json.dumps({"recordings_file": str(args.labels_jsonl), "windows": len(entries)}))


if __name__ == "__main__":
    main()
