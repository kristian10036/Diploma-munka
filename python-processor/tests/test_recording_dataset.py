import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from app.ml.recording_dataset import RecordingLabel, build_recording_windows, load_recording


def spectrum_frame(sequence: int) -> dict:
    powers = [-95.0] * 33
    powers[(sequence * 3) % len(powers)] = -35.0
    return {
        "schema_version": 1,
        "source_type": "mock",
        "session_id": "dataset-session",
        "timestamp": f"2026-06-19T12:00:0{sequence}.000Z",
        "sequence": sequence,
        "start_frequency_hz": 2_400_000_000,
        "stop_frequency_hz": 2_432_000_000,
        "step_frequency_hz": 1_000_000,
        "num_points": len(powers),
        "power_unit": "dBm",
        "powers_dbm": powers,
    }


class RecordingDatasetTest(unittest.TestCase):
    def create_recording(self, root: Path) -> Path:
        recording = root / "recording-a"
        recording.mkdir()
        frame_bytes = "".join(json.dumps(spectrum_frame(index)) + "\n" for index in range(4)).encode()
        (recording / "frames.ndjson").write_bytes(frame_bytes)
        (recording / "checksum.sha256").write_text(
            hashlib.sha256(frame_bytes).hexdigest() + "  frames.ndjson\n", encoding="ascii"
        )
        (recording / "metadata.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "recording_id": "recording-a",
                    "session_id": "dataset-session",
                    "source_type": "mock",
                    "frame_file": "frames.ndjson",
                    "frame_count": 4,
                }
            ),
            encoding="utf-8",
        )
        return recording

    def test_builds_atomic_windows_with_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            recording = self.create_recording(root)
            entries = build_recording_windows(
                RecordingLabel(recording, "unknown", "controlled_simulation", "unit fixture"),
                root / "processed",
                time_bins=2,
                frequency_bins=16,
                stride=2,
            )
            self.assertEqual(len(entries), 2)
            self.assertTrue(all(item["recording_id"] == "recording-a" for item in entries))
            self.assertTrue(all(item["provenance"] == "unit fixture" for item in entries))
            sample = np.load(entries[0]["processed_path"])
            self.assertEqual(sample["spectrogram"].shape, (2, 16))

    def test_rejects_checksum_mismatch_and_weak_label(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            recording = self.create_recording(root)
            weak = RecordingLabel(recording, "unknown", "weak_label", "Kismet time context")
            with self.assertRaisesRegex(ValueError, "weak labels"):
                build_recording_windows(weak, root / "processed", time_bins=2)
            (recording / "frames.ndjson").write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                load_recording(recording)


if __name__ == "__main__":
    unittest.main()
