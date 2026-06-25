import os
import unittest
from unittest.mock import patch

from app.rf_agent_client import (
    RfAgentSettings,
    RfAgentUnavailable,
    request_rf_agent,
    rf_agent_status,
)


class RfAgentClientTest(unittest.TestCase):
    def test_disabled_status_is_non_fatal(self):
        settings = RfAgentSettings(False, "http://rf-agent:8765", 1.0)
        status = rf_agent_status(settings)
        self.assertTrue(status["implemented"])
        self.assertEqual(status["status"], "disabled")
        with self.assertRaises(RfAgentUnavailable):
            request_rf_agent(settings, "/status")

    def test_environment_is_bounded(self):
        with patch.dict(
            os.environ,
            {
                "RF_AGENT_INTEGRATION_ENABLED": "true",
                "RF_AGENT_URL": "http://localhost:9876/",
                "RF_AGENT_TIMEOUT_SECONDS": "999",
            },
        ):
            settings = RfAgentSettings.from_env()
        self.assertTrue(settings.enabled)
        self.assertEqual(settings.base_url, "http://localhost:9876")
        self.assertEqual(settings.timeout_seconds, 30.0)

    def test_path_validation(self):
        settings = RfAgentSettings(True, "http://127.0.0.1:1", 0.5)
        with self.assertRaises(ValueError):
            request_rf_agent(settings, "status")


if __name__ == "__main__":
    unittest.main()
