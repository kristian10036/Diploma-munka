import io
import unittest

from fastapi import HTTPException, UploadFile

from app.utils.uploads import (
    detect_reference_image,
    read_bounded_upload,
    reject_binary_text_payload,
)


class UploadBoundaryTests(unittest.TestCase):
    @staticmethod
    def _upload(payload: bytes, filename: str = "upload.bin") -> UploadFile:
        return UploadFile(filename=filename, file=io.BytesIO(payload))

    def test_bounded_reader_returns_payload_at_limit(self):
        payload = read_bounded_upload(
            self._upload(b"abcd"),
            max_bytes=4,
            empty_detail="empty",
            too_large_detail="large",
        )
        self.assertEqual(payload, b"abcd")

    def test_bounded_reader_rejects_empty_and_oversized(self):
        with self.assertRaises(HTTPException) as empty:
            read_bounded_upload(
                self._upload(b""),
                max_bytes=4,
                empty_detail="empty",
                too_large_detail="large",
            )
        self.assertEqual(empty.exception.status_code, 400)
        with self.assertRaises(HTTPException) as large:
            read_bounded_upload(
                self._upload(b"abcde"),
                max_bytes=4,
                empty_detail="empty",
                too_large_detail="large",
            )
        self.assertEqual(large.exception.status_code, 413)

    def test_binary_text_payload_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            reject_binary_text_payload(b"header\x00value", label="Teszt")
        self.assertEqual(raised.exception.status_code, 415)

    def test_image_detection_uses_magic_bytes(self):
        png = detect_reference_image(b"\x89PNG\r\n\x1a\nrest", "wrong.bmp")
        bmp = detect_reference_image(b"BMrest", "wrong.png")
        self.assertEqual(png.content_type, "image/png")
        self.assertEqual(bmp.content_type, "image/bmp")
        with self.assertRaises(HTTPException) as raised:
            detect_reference_image(b"GIF89a", "fake.png")
        self.assertEqual(raised.exception.status_code, 415)


if __name__ == "__main__":
    unittest.main()
