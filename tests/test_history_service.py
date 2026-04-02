import unittest
from unittest import mock

from app.services.history_service import (
    PdfExportUnavailableError,
    export_history_as_pdf,
    format_history_as_text,
)


class HistoryServiceTests(unittest.TestCase):
    def test_format_history_as_text_preserves_blocks(self):
        rendered = format_history_as_text(
            [
                {
                    "timestamp": "2026-04-02 10:00:00",
                    "question": "Hoc phi ky nay la bao nhieu?",
                    "answer": "Can doi chieu theo nam hoc va he dao tao.",
                }
            ]
        )

        self.assertIn("[2026-04-02 10:00:00]", rendered)
        self.assertIn("User: Hoc phi ky nay la bao nhieu?", rendered)
        self.assertIn("Bot: Can doi chieu theo nam hoc va he dao tao.", rendered)

    def test_export_history_as_pdf_fails_gracefully_without_reportlab(self):
        original_import = __import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name.startswith("reportlab"):
                raise ImportError("missing reportlab")
            return original_import(name, globals, locals, fromlist, level)

        with mock.patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaises(PdfExportUnavailableError):
                export_history_as_pdf("user-1")


if __name__ == "__main__":
    unittest.main()
