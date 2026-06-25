from __future__ import annotations

import unittest

from app.services.sdrangel.iq_pipeline import (
    DataPlaneState,
    IqDataPlane,
    IqDataPlaneConfig,
    IqPacket,
    MockIqSink,
    MockIqSource,
    run_mock_pipeline,
)


class IqDataPlaneTests(unittest.TestCase):
    def test_config_states_are_honest(self):
        disabled = IqDataPlaneConfig(False, "not_configured", "", "cf32_le", 0)
        self.assertEqual(disabled.initial_state(), DataPlaneState.DISABLED)
        missing = IqDataPlaneConfig(True, "not_configured", "", "cf32_le", 0)
        self.assertEqual(missing.initial_state(), DataPlaneState.NOT_CONFIGURED)
        configured = IqDataPlaneConfig(True, "network", "udp://127.0.0.1:9999", "cf32_le", 48_000)
        self.assertEqual(configured.initial_state(), DataPlaneState.CONFIGURED_NOT_TESTED)

    def test_mock_source_to_sink(self):
        result = run_mock_pipeline(packet_count=5)
        self.assertTrue(result["drained"])
        self.assertEqual(result["published"], 5)
        self.assertEqual(result["status_before_stop"]["status"], "ready")
        self.assertFalse(result["status_before_stop"]["hardware_tested"])

    def test_bounded_queue_drop_oldest(self):
        config = IqDataPlaneConfig(
            True,
            "mock",
            "memory://sink",
            "cf32_le",
            48_000,
            queue_size=1,
            drop_policy="drop_oldest",
        )
        pipeline = IqDataPlane(config, MockIqSink())
        packets = list(MockIqSource(packet_count=2, samples_per_packet=4).packets())
        self.assertTrue(pipeline.enqueue(packets[0]))
        self.assertTrue(pipeline.enqueue(packets[1]))
        self.assertEqual(pipeline.stats.packets_dropped, 1)
        self.assertEqual(pipeline.status()["queue_depth"], 1)

    def test_sequence_gap_is_counted(self):
        config = IqDataPlaneConfig(True, "mock", "memory://sink", "cf32_le", 48_000)
        pipeline = IqDataPlane(config, MockIqSink())
        first = next(iter(MockIqSource(packet_count=1).packets()))
        second = IqPacket(
            protocol_version=first.protocol_version,
            sample_format=first.sample_format,
            sample_rate_hz=first.sample_rate_hz,
            center_frequency_hz=first.center_frequency_hz,
            timestamp_ns=first.timestamp_ns + 1,
            sequence=3,
            samples=first.samples,
        )
        pipeline.enqueue(first)
        pipeline.enqueue(second)
        self.assertEqual(pipeline.stats.sequence_gaps, 2)


if __name__ == "__main__":
    unittest.main()
