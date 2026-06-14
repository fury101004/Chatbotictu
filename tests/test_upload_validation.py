from __future__ import annotations

import unittest

from services.content.upload_validation import UploadValidationError, validate_text_upload


class UploadValidationTests(unittest.TestCase):
    def validate(self, filename: str, content: bytes, content_type: str = "text/plain"):
        return validate_text_upload(
            filename=filename,
            content=content,
            content_type=content_type,
            max_size_bytes=32,
        )

    def test_accepts_supported_utf8_markdown(self) -> None:
        result = self.validate("guide.md", b"# Guide\n\nNoi dung", "text/markdown")

        self.assertEqual(result.filename, "guide.md")
        self.assertEqual(result.text, "# Guide\n\nNoi dung")

    def test_rejects_unsupported_extension(self) -> None:
        with self.assertRaisesRegex(UploadValidationError, "unsupported file type"):
            self.validate("guide.pdf", b"plain text", "application/pdf")

    def test_rejects_empty_file(self) -> None:
        with self.assertRaisesRegex(UploadValidationError, "empty"):
            self.validate("guide.md", b"", "text/markdown")

    def test_rejects_binary_signature_even_with_text_extension(self) -> None:
        with self.assertRaisesRegex(UploadValidationError, "content signature"):
            self.validate("guide.md", b"%PDF-1.7 fake", "text/markdown")

    def test_rejects_extension_mime_mismatch(self) -> None:
        with self.assertRaisesRegex(UploadValidationError, "MIME"):
            self.validate("guide.md", b"# Guide", "application/pdf")

    def test_rejects_dangerous_filename(self) -> None:
        with self.assertRaisesRegex(UploadValidationError, "dangerous filename"):
            self.validate("../guide.md", b"# Guide", "text/markdown")

    def test_rejects_decode_error(self) -> None:
        with self.assertRaisesRegex(UploadValidationError, "UTF-8"):
            self.validate("guide.txt", b"\xff\xfe\xfd", "text/plain")

    def test_rejects_file_over_size_limit(self) -> None:
        with self.assertRaisesRegex(UploadValidationError, "too large"):
            self.validate("guide.txt", b"a" * 33, "text/plain")


if __name__ == "__main__":
    unittest.main()
