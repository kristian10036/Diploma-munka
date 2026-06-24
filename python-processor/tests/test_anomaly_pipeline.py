from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

import numpy as np

from app.services.anomaly import (
    OnlineAnomalyPipeline,
    SpectrumAnomalyConfig,
    SpectrumAnomalyDetector,
    SpectrumEnvelope,
    detect_bluetooth_anomalies,
    detect_wifi_anomalies,
)


class SpectrumDetectorTests(unittest.TestCase):
    def setUp(self):
        self.config = SpectrumAnomalyConfig(
            history_frames=12,
            warmup_frames=4,
            peak_delta_db=8,
            robust_sigma_multiplier=5,
            noise_floor_shift_db=5,
            occupancy_change_fraction=0.1,
            narrowband_max_hz=500_000,
            persistence_frames=3,
            bandwidth_ratio_change=2.0,
            cooldown_frames=2,
        )
        self.detector = SpectrumAnomalyDetector(self.config)
        self.freqs = np.arange(100_000_000, 101_000_000, 10_000, dtype=np.int64)

    def _warmup(self):
        for index in range(4):
            noise = np.full(len(self.freqs), -95.0) + (index % 2) * 0.2
            self.detector.process(self.freqs, noise, sequence=index)

    def test_new_peak_and_burst(self):
        self._warmup()
        powers = np.full(len(self.freqs), -95.0)
        powers[50] = -55.0
        detections = self.detector.process(self.freqs, powers, sequence=4)
        classes = {item.class_name for item in detections}
        self.assertIn("new_peak_above_reference", classes)
        self.assertIn("short_burst", classes)
        peak = next(item for item in detections if item.class_name == "new_peak_above_reference")
        self.assertEqual(peak.center_frequency_hz, int(self.freqs[50]))
        self.assertGreaterEqual(peak.confidence or 0, 0.8)

    def test_noise_floor_shift(self):
        self._warmup()
        detections = self.detector.process(self.freqs, np.full(len(self.freqs), -80.0), sequence=4)
        self.assertIn("noise_floor_shift", {item.class_name for item in detections})

    def test_sequence_gap_is_technical_event(self):
        self.detector.process(self.freqs, np.full(len(self.freqs), -95.0), sequence=1)
        detections = self.detector.process(self.freqs, np.full(len(self.freqs), -95.0), sequence=4)
        gap = next(item for item in detections if item.class_name == "sequence_gap")
        self.assertEqual(gap.entity_domain, "technical")
        self.assertEqual(gap.evidence["gap"], 2)

    def test_invalid_frame_rejected(self):
        with self.assertRaisesRegex(ValueError, "non_monotonic"):
            self.detector.process([2, 1], [-90, -80])


class PassiveDetectorTests(unittest.TestCase):
    def test_wifi_encryption_and_location_changes(self):
        history = [{
            "bssid": "AA:BB:CC:DD:EE:FF", "ssid": "Office", "encryption": "WPA2",
            "location_id": "A", "rssi_dbm": -70, "vendor": "Acme",
        }]
        current = {
            "bssid": "AA:BB:CC:DD:EE:FF", "ssid": "Office", "encryption": "open",
            "location_id": "B", "rssi_dbm": -40, "vendor": "Other",
        }
        classes = {item.class_name for item in detect_wifi_anomalies(current, history)}
        self.assertIn("ssid_encryption_changed", classes)
        self.assertIn("device_seen_multiple_locations", classes)
        self.assertIn("rssi_behavior_changed", classes)
        self.assertIn("vendor_property_mismatch", classes)

    def test_ble_services_and_randomized_identity_warning(self):
        history = [{
            "mac_address": "11:22:33:44:55:66", "location_id": "A",
            "service_uuids": ["180D"], "rssi_dbm": -80,
        }]
        current = {
            "mac_address": "11:22:33:44:55:66", "location_id": "B",
            "service_uuids": ["180D", "180F"], "rssi_dbm": -50,
        }
        detections = detect_bluetooth_anomalies(current, history)
        classes = {item.class_name for item in detections}
        self.assertIn("new_service_uuid", classes)
        self.assertIn("ble_seen_multiple_locations", classes)
        multi = next(item for item in detections if item.class_name == "ble_seen_multiple_locations")
        self.assertEqual(multi.evidence["certainty"], "cautious")


class OnlinePipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_pipeline_is_bounded_and_non_blocking(self):
        pipeline = OnlineAnomalyPipeline(queue_size=2)

        async def run_inline(func, *args, **kwargs):
            return func(*args, **kwargs)

        try:
            frequencies = tuple(range(100_000_000, 100_010_000, 100))
            powers = tuple([-95.0] * len(frequencies))
            accepted = pipeline.submit_nowait(SpectrumEnvelope(
                frequencies, powers, 1, "2026-01-01T00:00:00Z", "mock"
            ))
            accepted_second = pipeline.submit_nowait(SpectrumEnvelope(
                frequencies, powers, 2, "2026-01-01T00:00:01Z", "mock"
            ))
            dropped = pipeline.submit_nowait(SpectrumEnvelope(
                frequencies, powers, 3, "2026-01-01T00:00:02Z", "mock"
            ))
            self.assertTrue(accepted)
            self.assertTrue(accepted_second)
            self.assertFalse(dropped)
            self.assertEqual(pipeline.dropped_frames, 1)
            with patch("app.services.anomaly.pipeline.asyncio.to_thread", side_effect=run_inline):
                await pipeline.start()
                await asyncio.wait_for(pipeline.queue.join(), timeout=2)
            self.assertEqual(pipeline.processed_frames, 2)
        finally:
            await pipeline.stop()


if __name__ == "__main__":
    unittest.main()
