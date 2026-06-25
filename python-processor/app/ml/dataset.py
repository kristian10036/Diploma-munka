from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetItem:
    item_id: str
    recording_id: str
    session_id: str
    label: str

    @property
    def group_id(self) -> str:
        return self.recording_id or self.session_id


def grouped_split(
    items: list[DatasetItem],
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
    seed: str = "rf-dataset-v1",
) -> dict[str, list[DatasetItem]]:
    """Deterministic group split; a recording/session can occur in only one partition."""
    if not 0 < train_fraction < 1 or not 0 <= validation_fraction < 1:
        raise ValueError("invalid split fractions")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("train + validation fraction must be below 1")
    result: dict[str, list[DatasetItem]] = {"train": [], "validation": [], "test": []}
    assignments: dict[str, str] = {}
    for item in items:
        if not item.group_id:
            raise ValueError("every item requires a recording_id or session_id")
        digest = hashlib.sha256(f"{seed}:{item.group_id}".encode()).digest()
        value = int.from_bytes(digest[:8], "big") / float(2**64)
        partition = (
            "train"
            if value < train_fraction
            else ("validation" if value < train_fraction + validation_fraction else "test")
        )
        previous = assignments.setdefault(item.group_id, partition)
        if previous != partition:
            raise AssertionError("group leakage detected")
        result[partition].append(item)
    return result
