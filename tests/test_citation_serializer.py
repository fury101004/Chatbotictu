from __future__ import annotations

import unittest

from models.chat import RetrievedChunk
from services.rag.citation_serializer import ADMIN_AUDIENCE, serialize_citations, serialize_chat_payload


class CitationSerializerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.chunk = RetrievedChunk(
            document=("Điều kiện xét học bổng dành cho sinh viên đủ điểm học tập và rèn luyện. " * 12),
            metadata={
                "source": "student_handbooks/8. SO TAY SINH VIEN 2025-2026.md",
                "source_path": r"E:\private\data\student_handbook.md",
                "title": "Điều kiện học bổng",
                "chapter": "Chương 4",
                "page_number": 24,
                "academic_year": "2025-2026",
                "chunk_id": "chunk-secret-debug-id",
                "api_key": "must-not-leak",
                "system_prompt": "must-not-leak",
            },
        )

    def test_user_citation_is_clean_and_short(self) -> None:
        citation = serialize_citations([self.chunk])[0]

        self.assertEqual(citation["title"], "Điều kiện học bổng")
        self.assertEqual(citation["chapter"], "Chương 4")
        self.assertEqual(citation["page_number"], 24)
        self.assertEqual(citation["year"], "2025-2026")
        self.assertLessEqual(len(citation["excerpt"]), 283)
        self.assertNotIn("source", citation)
        self.assertNotIn("source_path", citation)
        self.assertNotIn("metadata", citation)
        self.assertNotIn("api_key", str(citation))
        self.assertNotIn("system_prompt", str(citation))

    def test_admin_citation_keeps_debug_detail_but_removes_secrets_and_absolute_path(self) -> None:
        citation = serialize_citations([self.chunk], audience=ADMIN_AUDIENCE)[0]

        self.assertEqual(citation["source"], "student_handbooks/8. SO TAY SINH VIEN 2025-2026.md")
        self.assertEqual(citation["metadata"]["chunk_id"], "chunk-secret-debug-id")
        self.assertNotIn("source_path", citation)
        self.assertNotIn("source_path", citation["metadata"])
        self.assertNotIn("api_key", citation["metadata"])
        self.assertNotIn("system_prompt", citation["metadata"])

    def test_chat_payload_projects_user_and_admin_citations(self) -> None:
        user_details = serialize_citations([self.chunk])
        admin_details = serialize_citations([self.chunk], audience=ADMIN_AUDIENCE)
        payload = {
            "response": "ok",
            "sources": ["student_handbooks/8. SO TAY SINH VIEN 2025-2026.md"],
            "source_details": user_details,
            "_admin_source_details": admin_details,
        }

        user_payload = serialize_chat_payload(payload, audience="user")
        admin_payload = serialize_chat_payload(payload, audience=ADMIN_AUDIENCE)

        self.assertNotIn("sources", user_payload)
        self.assertNotIn("_admin_source_details", user_payload)
        self.assertNotIn("source", user_payload["source_details"][0])
        self.assertIn("sources", admin_payload)
        self.assertIn("source", admin_payload["source_details"][0])
        self.assertNotIn("_admin_source_details", admin_payload)


if __name__ == "__main__":
    unittest.main()
