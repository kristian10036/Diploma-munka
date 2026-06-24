"""A /api/rf-agent/sdrangel/demod/update élő frissítő végpont tesztjei.

A végpont csak proxy: a séma-validációt és a PATCH továbbítását ellenőrizzük,
az RF-agent hívást mockoljuk (nem kell futó rf-agent).
"""
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.routers.rf_agent import update_sdrangel_demod
from app.schemas import SdrangelDemodUpdateRequest

VALID = {
    "device_set_index": 0,
    "channel_index": 2,
    "demodulator": "NFM",
    "frequency_hz": 145_500_000,
    "bandwidth_hz": 12500,
    "squelch_db": -60,
    "volume": 1.0,
    "input_frequency_offset_hz": 500000,
}


class SdrangelDemodUpdateTest(unittest.TestCase):
    def test_valid_update_proxies_patch(self):
        captured = {}

        def fake_proxy(settings, path, *, method="GET", body=None):
            captured["path"] = path
            captured["method"] = method
            captured["body"] = body
            return {"status": "ok", "channel_index": 2, "applied_settings": {"inputFrequencyOffset": 500000}}

        with patch("app.routers.rf_agent.request_rf_agent", side_effect=fake_proxy):
            response = update_sdrangel_demod(SdrangelDemodUpdateRequest(**VALID))

        self.assertEqual(captured["path"], "/sdrangel/demod/update")
        self.assertEqual(captured["method"], "PATCH")
        # A helyes mezők jutnak el az rf-agentig.
        self.assertEqual(captured["body"]["channel_index"], 2)
        self.assertEqual(captured["body"]["bandwidth_hz"], 12500)
        self.assertEqual(captured["body"]["input_frequency_offset_hz"], 500000)
        self.assertIn("requested", response)

    def test_invalid_bandwidth_rejected(self):
        with self.assertRaises(ValidationError):
            SdrangelDemodUpdateRequest(**dict(VALID, bandwidth_hz=10))  # < 100 Hz minimum

    def test_missing_channel_index_rejected(self):
        payload = dict(VALID)
        payload.pop("channel_index")
        with self.assertRaises(ValidationError):
            SdrangelDemodUpdateRequest(**payload)

    def test_negative_channel_index_rejected(self):
        with self.assertRaises(ValidationError):
            SdrangelDemodUpdateRequest(**dict(VALID, channel_index=-1))

    def test_optional_fields_omitted_when_absent(self):
        captured = {}

        def fake_proxy(settings, path, *, method="GET", body=None):
            captured["body"] = body
            return {"status": "ok"}

        minimal = {"device_set_index": 0, "channel_index": 1, "demodulator": "AM"}
        with patch("app.routers.rf_agent.request_rf_agent", side_effect=fake_proxy):
            response = update_sdrangel_demod(SdrangelDemodUpdateRequest(**minimal))

        self.assertEqual(response["status"], "ok")
        # exclude_none: a meg nem adott opcionális mezők nem mennek tovább.
        self.assertNotIn("bandwidth_hz", captured["body"])
        self.assertNotIn("frequency_hz", captured["body"])

    def test_rf_agent_unavailable_returns_503(self):
        from app.rf_agent_client import RfAgentUnavailable

        def fake_proxy(settings, path, *, method="GET", body=None):
            raise RfAgentUnavailable("rf_agent_integration_disabled")

        with patch("app.routers.rf_agent.request_rf_agent", side_effect=fake_proxy):
            with self.assertRaises(HTTPException) as exc:
                update_sdrangel_demod(SdrangelDemodUpdateRequest(**VALID))
        self.assertEqual(exc.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
