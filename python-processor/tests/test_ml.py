import unittest

import numpy as np

from app.ml.classical import NearestCentroidRfClassifier
from app.ml.classifier import RuleBasedRfClassifier
from app.ml.dataset import DatasetItem, grouped_split
from app.ml.preprocessing import SpectrogramPreprocessor
from app.ml.metrics import classification_metrics


def frame(powers, sequence=0):
    return {
        "schema_version": 1,
        "source_type": "mock",
        "session_id": "session-a",
        "sequence": sequence,
        "start_frequency_hz": 2_400_000_000,
        "stop_frequency_hz": 2_400_000_000 + 1_000_000 * (len(powers) - 1),
        "step_frequency_hz": 1_000_000,
        "num_points": len(powers),
        "power_unit": "dBm",
        "powers_dbm": list(map(float, powers)),
    }


class MlPipelineTest(unittest.TestCase):
    def test_preprocessor_rejects_non_spectrum_input(self):
        with self.assertRaisesRegex(ValueError, "missing SpectrumFrame"):
            SpectrogramPreprocessor().prepare([{"rssi": -42, "bssid": "00:11"}])

    def test_rule_baseline_noise_and_narrowband(self):
        classifier = RuleBasedRfClassifier()
        noise = classifier.classify([frame(np.full(101, -90.0))])
        self.assertEqual(noise["predicted_class"], "noise")
        narrow = np.full(101, -95.0)
        narrow[50] = -30.0
        result = classifier.classify([frame(narrow)])
        self.assertEqual(result["predicted_class"], "narrowband_unknown")
        self.assertGreater(result["confidence"], 0.5)

    def test_grouped_split_has_no_recording_leakage(self):
        items = [
            DatasetItem(f"item-{index}", f"recording-{index // 3}", "session", "noise")
            for index in range(30)
        ]
        split = grouped_split(items)
        memberships = {}
        for partition, values in split.items():
            for item in values:
                memberships.setdefault(item.recording_id, set()).add(partition)
        self.assertTrue(all(len(partitions) == 1 for partitions in memberships.values()))
        self.assertEqual(sum(map(len, split.values())), len(items))

    def test_metrics_include_macro_f1_and_confusion_matrix(self):
        metrics = classification_metrics(
            ["noise", "noise", "unknown", "unknown"],
            ["noise", "unknown", "unknown", "unknown"],
            ["noise", "unknown"],
        )
        self.assertEqual(metrics["accuracy"], 0.75)
        self.assertEqual(metrics["confusion_matrix"], [[1, 1], [0, 2]])
        self.assertIn("macro_f1", metrics)

    def test_classical_baseline(self):
        model = NearestCentroidRfClassifier().fit(
            np.asarray([[0.0, 0.1], [0.1, 0.0], [10.0, 9.9], [9.9, 10.0]]),
            ["noise", "noise", "wideband_unknown", "wideband_unknown"],
        )
        self.assertEqual(model.predict([[0.05, 0.05], [10.0, 10.0]]), ["noise", "wideband_unknown"])
        self.assertTrue(np.allclose(model.predict_proba([[1.0, 1.0]]).sum(axis=1), 1.0))


if __name__ == "__main__":
    unittest.main()
