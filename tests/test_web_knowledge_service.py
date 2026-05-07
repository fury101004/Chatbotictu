from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from models.chat import RetrievedChunk
from services.content.web_knowledge_service import save_web_search_answer, search_trusted_web_knowledge


class WebKnowledgeServiceTests(unittest.TestCase):
    def test_official_web_answer_is_saved_as_trusted_and_searchable_after_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "web_kb.db"
            chunk = RetrievedChunk(
                document="ICTU công bố thông báo tuyển sinh mới nhất trên website chính thức.",
                metadata={
                    "source_type": "web_search",
                    "source": "https://ictu.edu.vn/tuyen-sinh-moi-nhat",
                    "title": "Thông báo tuyển sinh ICTU",
                },
            )

            with (
                patch("config.db.DB_PATH", db_path),
                patch("services.content.web_knowledge_service.WEB_KB_TRUSTED_THRESHOLD", 1),
            ):
                result = save_web_search_answer(
                    question="ICTU tuyển sinh mới nhất có gì?",
                    answer="ICTU có thông báo tuyển sinh mới nhất trên website chính thức.",
                    chunks=[chunk],
                    rag_tool="student_faq_rag",
                    rag_route="router_faq",
                    llm_model="groq:llama-3.1-8b-instant",
                )
                matches = search_trusted_web_knowledge("tuyển sinh ICTU mới nhất")

            self.assertTrue(result["saved"])
            self.assertEqual(result["status"], "trusted")
            self.assertEqual(len(matches), 1)
            self.assertIn("tuyển sinh", matches[0].answer)
            self.assertEqual(matches[0].sources, ["https://ictu.edu.vn/tuyen-sinh-moi-nhat"])

    def test_external_web_answer_is_candidate_and_not_prioritized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "web_kb.db"
            chunk = RetrievedChunk(
                document="Một trang ngoài nhắc đến ICTU.",
                metadata={
                    "source_type": "web_search",
                    "source": "https://example.com/ictu",
                    "title": "Tin ngoài ICTU",
                },
            )

            with (
                patch("config.db.DB_PATH", db_path),
                patch("services.content.web_knowledge_service.WEB_KB_TRUSTED_THRESHOLD", 1),
            ):
                result = save_web_search_answer(
                    question="ICTU có tin gì mới?",
                    answer="Một trang ngoài có nhắc đến ICTU.",
                    chunks=[chunk],
                )
                matches = search_trusted_web_knowledge("tin ICTU mới")

            self.assertTrue(result["saved"])
            self.assertEqual(result["status"], "candidate")
            self.assertEqual(matches, [])

    def test_save_web_search_answer_returns_stable_entry_id_on_upsert(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "web_kb.db"
            chunk = RetrievedChunk(
                document="Thong bao hoc phi moi nhat cua ICTU.",
                metadata={
                    "source_type": "web_search",
                    "source": "https://ictu.edu.vn/hoc-phi-moi",
                    "title": "Hoc phi ICTU",
                },
            )

            with (
                patch("config.db.DB_PATH", db_path),
                patch("services.content.web_knowledge_service.WEB_KB_TRUSTED_THRESHOLD", 1),
            ):
                first = save_web_search_answer(
                    question="Hoc phi ICTU moi nhat la gi?",
                    answer="Thong bao ban dau ve hoc phi ICTU moi nhat.",
                    chunks=[chunk],
                )
                second = save_web_search_answer(
                    question="Hoc phi ICTU moi nhat la gi?",
                    answer="Thong bao cap nhat lan hai ve hoc phi ICTU moi nhat.",
                    chunks=[chunk],
                )

            self.assertTrue(first["saved"])
            self.assertTrue(second["saved"])
            self.assertIsNotNone(first["entry_id"])
            self.assertEqual(second["entry_id"], first["entry_id"])


if __name__ == "__main__":
    unittest.main()

