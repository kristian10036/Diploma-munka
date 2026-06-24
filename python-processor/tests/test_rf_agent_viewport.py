"""A /api/rf-agent/source/viewport proxy végpont tesztjei.

A végpont csak proxy: a séma-validációt és a POST továbbítását ellenőrizzük,
az RF-agent hívást mockoljuk (nem kell futó rf-agent).
"""
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.routers.rf_agent import configure_rf_agent_viewport
from app.schemas import ViewportRequest

VALID = {
    "request_id": "frontend-1700000000-abc123",
    "mode": "sweep",
    "center_frequency_hz": 433_920_000,
    "span_hz": 2_000_000,
    "maximum_points": 4800,
    "desired_rbw_hz": 416.6667,
}


class ConfigureRfAgentViewportTest(unittest.TestCase):
    def test_valid_request_proxies_post(self):
        captured = {}

        def fake_proxy(settings, path, *, method="GET", body=None):
            captured["path"] = path
            captured["method"] = method
            captured["body"] = body
            return {
                "schema_version": 1, "request_id": body["request_id"], "status": "accepted",
                "mode": body["mode"], "center_frequency_hz": body["center_frequency_hz"],
                "span_hz": body["span_hz"], "start_frequency_hz": 432_920_000,
                "stop_frequency_hz": 434_920_000, "step_frequency_hz": 417,
                "num_points": body["maximum_points"], "source_type": "mock",
                "hardware_execution": False,
            }

        with patch("app.routers.rf_agent.request_rf_agent", side_effect=fake_proxy):
            response = configure_rf_agent_viewport(ViewportRequest(**VALID))

        self.assertEqual(captured["path"], "/source/viewport")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["body"]["center_frequency_hz"], 433_920_000)
        self.assertEqual(captured["body"]["maximum_points"], 4800)
        self.assertAlmostEqual(captured["body"]["desired_rbw_hz"], 416.6667)
        self.assertEqual(response["status"], "accepted")

    def test_optional_desired_rbw_omitted_when_absent(self):
        captured = {}

        def fake_proxy(settings, path, *, method="GET", body=None):
            captured["body"] = body
            return {"status": "accepted"}

        minimal = dict(VALID)
        minimal.pop("desired_rbw_hz")
        with patch("app.routers.rf_agent.request_rf_agent", side_effect=fake_proxy):
            configure_rf_agent_viewport(ViewportRequest(**minimal))

        self.assertNotIn("desired_rbw_hz", captured["body"])

    def test_invalid_mode_rejected(self):
        with self.assertRaises(ValidationError):
            ViewportRequest(**dict(VALID, mode="continuous"))

    def test_non_positive_span_rejected(self):
        with self.assertRaises(ValidationError):
            ViewportRequest(**dict(VALID, span_hz=0))

    def test_too_few_points_rejected(self):
        with self.assertRaises(ValidationError):
            ViewportRequest(**dict(VALID, maximum_points=1))

    def test_missing_request_id_rejected(self):
        payload = dict(VALID)
        payload.pop("request_id")
        with self.assertRaises(ValidationError):
            ViewportRequest(**payload)

    def test_rf_agent_unavailable_returns_503(self):
        from app.rf_agent_client import RfAgentUnavailable

        def fake_proxy(settings, path, *, method="GET", body=None):
            raise RfAgentUnavailable("rf_agent_integration_disabled")

        with patch("app.routers.rf_agent.request_rf_agent", side_effect=fake_proxy):
            with self.assertRaises(HTTPException) as exc:
                configure_rf_agent_viewport(ViewportRequest(**VALID))
        self.assertEqual(exc.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
