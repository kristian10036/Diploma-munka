from datetime import datetime, timezone
from uuid import UUID
import unittest

from app.utils.pagination import decode_time_uuid_cursor, encode_time_uuid_cursor


class PaginationCursorTests(unittest.TestCase):
    def test_roundtrip(self):
        timestamp = datetime(2026, 6, 20, 12, 30, 15, 123456, tzinfo=timezone.utc)
        identifier = UUID("12345678-1234-5678-9234-567812345678")
        cursor = encode_time_uuid_cursor(timestamp, identifier)
        decoded_time, decoded_id = decode_time_uuid_cursor(cursor)
        self.assertEqual(decoded_time, timestamp)
        self.assertEqual(decoded_id, identifier)

    def test_invalid_cursor(self):
        with self.assertRaisesRegex(ValueError, "invalid_pagination_cursor"):
            decode_time_uuid_cursor("not-a-valid-cursor")


if __name__ == "__main__":
    unittest.main()
