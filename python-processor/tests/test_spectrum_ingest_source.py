import json
import unittest

from app.config import SpectrumSettings
from app.spectrum.sources.spectrum_ingest import SpectrumIngestWebSocketSource


def frame(**changes):
    value = {
        "schema_version": 1,
        "sensor_id": "aaronia-v6-01",
        "source_type": "aaronia",
        "source_device": "A3-x-83000043.xxaaaxbx",
        "device_model": "SPECTRAN V6 TEST",
        "measurement_mode": "sweepsa",
        "session_id": "aaronia-live",
        "timestamp": "2026-06-21T12:00:00.000Z",
        "sequence": 7,
        "start_frequency_hz": 70_000_000,
        "step_frequency_hz": 2_965_000_000,
        "num_points": 3,
        "point_count": 3,
        "powers_dbm": [-100.0, -80.0, -95.0],
        "flags": {"overflow": False, "dropped": False, "inaccurate": False},
    }
    value.update(changes)
    return value


class SpectrumIngestSourceTests(unittest.TestCase):
    def test_parses_real_spectrum_frame_contract(self):
        parsed = SpectrumIngestWebSocketSource._parse_frame(json.dumps(frame()))
        self.assertEqual(parsed.source_mode, "aaronia")
        self.assertEqual(parsed.sequence, 7)
        self.assertEqual(parsed.source_device, "A3-x-83000043.xxaaaxbx")
        self.assertEqual([point.frequency_mhz for point in parsed.points], [70.0, 3035.0, 6000.0])

    def test_rejects_shape_mismatch(self):
        with self.assertRaisesRegex(ValueError, "shape"):
            SpectrumIngestWebSocketSource._parse_frame(
                json.dumps(frame(num_points=4, point_count=4))
            )

    def test_configuration_uses_fixed_environment_url(self):
        settings = SpectrumSettings.from_env()
        source = SpectrumIngestWebSocketSource(settings)
        self.assertEqual(source.settings.spectrum_ingest_ws_url, settings.spectrum_ingest_ws_url)


if __name__ == "__main__":
    unittest.main()
