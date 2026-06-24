import unittest

from app.services.known_signals import evaluate_known_signal


class KnownSignalMatchingTest(unittest.TestCase):
    def setUp(self):
        self.profile = {"id": "known-1", "center_frequency_hz": 100_000_000,
                        "frequency_tolerance_hz": 10_000, "bandwidth_hz": 25_000,
                        "expected_power_min_dbm": -70, "expected_power_max_dbm": -30,
                        "modulation": "NFM", "source_type": "mock", "status": "active",
                        "suppress_alerts": True}

    def test_matching_profile_can_suppress(self):
        result = evaluate_known_signal(self.profile, {"center_frequency_hz": 100_005_000,
            "bandwidth_hz": 27_000, "power_dbm": -45, "modulation": "nfm", "source_type": "mock"})
        self.assertTrue(result["matched"])
        self.assertTrue(result["suppress_alert"])

    def test_frequency_only_does_not_suppress_when_properties_differ(self):
        result = evaluate_known_signal(self.profile, {"center_frequency_hz": 100_000_000,
            "bandwidth_hz": 100_000, "power_dbm": -10, "modulation": "AM", "source_type": "usrp"})
        self.assertFalse(result["matched"])
        self.assertFalse(result["suppress_alert"])
        self.assertIn("bandwidth", result["mismatches"])


if __name__ == "__main__":
    unittest.main()
