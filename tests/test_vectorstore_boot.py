from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from services.vector import vectorstore_boot


class VectorstoreBootTests(unittest.TestCase):
    def test_get_vectorstore_status_reports_sqlite_and_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vectorstore_dir = Path(temp_dir) / "vectorstore"
            vectorstore_dir.mkdir()
            (vectorstore_dir / "chroma.sqlite3").write_text("sqlite", encoding="utf-8")

            fake_collection = SimpleNamespace(name="markdown_docs_v2", count=lambda: 42)
            fake_client = SimpleNamespace(list_collections=lambda: [fake_collection])

            with (
                patch.object(vectorstore_boot.settings, "VECTORSTORE_DIR", vectorstore_dir),
                patch.object(vectorstore_boot.settings, "PROJECT_ROOT", Path(temp_dir)),
                patch("services.vector.vector_store_service.get_client", return_value=fake_client),
            ):
                status = vectorstore_boot.get_vectorstore_status()

            self.assertTrue(status["exists"])
            self.assertTrue(status["sqlite_exists"])
            self.assertEqual(status["collections"], 1)
            self.assertEqual(status["chunks"], 42)
            self.assertGreaterEqual(status["file_count"], 1)


if __name__ == "__main__":
    unittest.main()
