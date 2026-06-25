import hashlib
import os
import unittest
from unittest.mock import patch

from app.security import SecuritySettings


class SecuritySettingsTests(unittest.TestCase):
    def test_demo_defaults_are_valid(self):
        settings = SecuritySettings(
            app_mode="demo",
            allow_synthetic_fallback=True,
            auth_mode="disabled",
            anonymous_read=True,
            operator_token_sha256="",
            admin_token_sha256="",
            max_request_bytes=1024,
        )
        settings.validate()

    def test_production_requires_database_and_token_auth(self):
        settings = SecuritySettings(
            app_mode="production",
            allow_synthetic_fallback=False,
            auth_mode="disabled",
            anonymous_read=True,
            operator_token_sha256="",
            admin_token_sha256="",
            max_request_bytes=1024,
        )
        with patch.dict(
            os.environ, {"DATABASE_URL": "", "POSTGRES_PASSWORD": "safe-random-value"}, clear=False
        ):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL is required"):
                settings.validate()

    def test_invalid_request_size_has_clear_error(self):
        with patch.dict(os.environ, {"MAX_REQUEST_BYTES": "not-an-integer"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "MAX_REQUEST_BYTES must be an integer"):
                SecuritySettings.from_env()

    def test_sha256_token_hash_format(self):
        digest = hashlib.sha256(b"operator-secret").hexdigest()
        settings = SecuritySettings(
            app_mode="demo",
            allow_synthetic_fallback=True,
            auth_mode="api_token",
            anonymous_read=True,
            operator_token_sha256=digest,
            admin_token_sha256="",
            max_request_bytes=1024,
        )
        settings.validate()
        invalid = SecuritySettings(
            app_mode="demo",
            allow_synthetic_fallback=True,
            auth_mode="api_token",
            anonymous_read=True,
            operator_token_sha256="not-a-digest",
            admin_token_sha256="",
            max_request_bytes=1024,
        )
        with self.assertRaisesRegex(RuntimeError, "SHA-256"):
            invalid.validate()

    def test_production_rejects_synthetic_fallback(self):
        settings = SecuritySettings(
            app_mode="production",
            allow_synthetic_fallback=True,
            auth_mode="api_token",
            anonymous_read=True,
            operator_token_sha256=hashlib.sha256(b"operator-secret").hexdigest(),
            admin_token_sha256="",
            max_request_bytes=1024,
        )
        with self.assertRaisesRegex(RuntimeError, "ALLOW_SYNTHETIC_FALLBACK"):
            settings.validate()

    def test_app_profile_env_controls_mode_and_fallback(self):
        with patch.dict(
            os.environ,
            {"APP_PROFILE": "production", "ALLOW_SYNTHETIC_FALLBACK": "false"},
            clear=False,
        ):
            settings = SecuritySettings.from_env()
        self.assertEqual(settings.app_mode, "production")
        self.assertFalse(settings.allow_synthetic_fallback)


if __name__ == "__main__":
    unittest.main()
