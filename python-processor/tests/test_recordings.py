from __future__ import annotations

import json
import os
import tempfile
import unittest
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.recordings import (
    AudioRecordingReader,
    RecordingCatalog,
    RecordingSettings,
    RecordingStorage,
    SigMfRecordingReader,
    create_mock_audio_recording,
    create_mock_iq_recording,
)


class RecordingFormatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name) / "recordings"
        self.settings = RecordingSettings(
            root=root,
            quarantine_dir=root / ".quarantine",
            min_free_bytes=1,
            max_recording_bytes=10 * 1024 * 1024,
            max_duration_seconds=60,
            retention_days=30,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_mock_iq_sigmf_roundtrip_and_checksum(self):
        metadata = create_mock_iq_recording(self.settings, recording_id="iq-test", sample_count=256)
        self.assertEqual(metadata["recording_type"], "iq")
        self.assertTrue(metadata["mock"])
        reader = SigMfRecordingReader(self.settings.root / "iq-test")
        self.assertTrue(reader.verify_checksum())
        samples = list(reader.samples())
        self.assertEqual(len(samples), 256)
        self.assertAlmostEqual(abs(samples[0]), 1.0, places=5)
        sigmf = json.loads((self.settings.root / "iq-test" / "iq-test.sigmf-meta").read_text())
        self.assertEqual(sigmf["global"]["core:datatype"], "cf32_le")
        self.assertEqual(sigmf["captures"][0]["core:frequency"], 100_000_000)

    def test_iq_corruption_is_detected(self):
        metadata = create_mock_iq_recording(
            self.settings, recording_id="iq-corrupt", sample_count=32
        )
        data_path = self.settings.root / "iq-corrupt" / metadata["data_file"]
        with data_path.open("ab") as handle:
            handle.write(b"corrupt")
        reader = SigMfRecordingReader(self.settings.root / "iq-corrupt")
        self.assertFalse(reader.verify_checksum())

    def test_mock_audio_wav_roundtrip_and_checksum(self):
        metadata = create_mock_audio_recording(
            self.settings, recording_id="audio-test", duration_seconds=0.02
        )
        self.assertEqual(metadata["recording_type"], "audio")
        reader = AudioRecordingReader(self.settings.root / "audio-test")
        self.assertTrue(reader.verify_checksum())
        properties = reader.properties()
        self.assertEqual(properties["sample_rate"], 48_000)
        self.assertEqual(properties["channels"], 1)
        self.assertGreater(properties["frame_count"], 0)
        with wave.open(str(reader.audio_path), "rb") as handle:
            self.assertEqual(handle.getsampwidth(), 2)

    def test_catalog_supports_legacy_spectrum_and_new_types(self):
        create_mock_iq_recording(self.settings, recording_id="iq-item", sample_count=16)
        create_mock_audio_recording(self.settings, recording_id="audio-item", duration_seconds=0.01)
        spectrum = self.settings.root / "legacy-spectrum"
        spectrum.mkdir()
        frame_file = spectrum / "frames.ndjson"
        frame_file.write_text('{"schema_version":1}\n')
        import hashlib

        checksum = hashlib.sha256(frame_file.read_bytes()).hexdigest()
        (spectrum / "metadata.json").write_text(
            json.dumps(
                {
                    "recording_id": "legacy-spectrum",
                    "frame_file": "frames.ndjson",
                    "checksum_sha256": checksum,
                    "started_at": "2026-01-01T00:00:00Z",
                }
            )
        )
        items = RecordingCatalog(self.settings).list(verify_checksums=True)
        by_id = {item["recording_id"]: item for item in items}
        self.assertEqual(by_id["legacy-spectrum"]["recording_type"], "spectrum")
        self.assertEqual(by_id["legacy-spectrum"]["checksum_status"], "valid")
        self.assertEqual(by_id["iq-item"]["recording_type"], "iq")
        self.assertEqual(by_id["audio-item"]["recording_type"], "audio")

    def test_storage_low_disk_and_retention_are_non_destructive(self):
        settings = RecordingSettings(
            root=self.settings.root,
            quarantine_dir=self.settings.quarantine_dir,
            min_free_bytes=10**30,
            max_recording_bytes=1024,
            max_duration_seconds=1,
            retention_days=1,
        )
        storage = RecordingStorage(settings)
        with self.assertRaisesRegex(RuntimeError, "recording_low_disk"):
            storage.assert_can_start()
        old = settings.root / "old-recording"
        old.mkdir(parents=True)
        (old / "metadata.json").write_text("{}")
        timestamp = (datetime.now(timezone.utc) - timedelta(days=10)).timestamp()
        os.utime(old, (timestamp, timestamp))
        plan = storage.retention_plan()
        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["candidate_count"], 1)
        self.assertTrue(old.exists())


if __name__ == "__main__":
    unittest.main()
