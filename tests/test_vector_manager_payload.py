from __future__ import annotations

import unittest
from unittest.mock import patch

from services.document_service import get_vector_manager_payload


class _FakeCollection:
    def get(self, include=None):
        return {
            "ids": [
                "chunk-handbook",
                "chunk-policy",
                "chunk-faq",
                "chunk-bot-rule",
            ],
            "documents": [
                "Noi dung so tay sinh vien",
                "Noi dung quy dinh hoc phi",
                "Noi dung hoi dap email sinh vien",
                "Noi quy he thong",
            ],
            "metadatas": [
                {
                    "source": "uploads/student_handbook_rag/handbook.md",
                    "title": "So tay",
                    "level": 2,
                    "tool_name": "student_handbook_rag",
                },
                {
                    "source": "congvanquyetdinh/policy.md",
                    "title": "Hoc phi",
                    "level": 3,
                    "tool_name": "school_policy_rag",
                },
                {
                    "source": "congvanxettn/faq.md",
                    "title": "Email sinh vien",
                    "level": 1,
                },
                {
                    "source": "BOT_RULE",
                    "title": "Bot rule",
                    "level": 1,
                },
            ],
        }


class VectorManagerPayloadTests(unittest.TestCase):
    def test_payload_is_grouped_into_three_rag_tools(self) -> None:
        with patch("services.document_service.get_collection", return_value=_FakeCollection()):
            payload = get_vector_manager_payload(limit_per_file=10)

        self.assertEqual(payload["total_files"], 3)
        self.assertEqual(payload["total_chunks"], 3)
        self.assertEqual(len(payload["tool_groups"]), 3)

        handbook_group, policy_group, faq_group = payload["tool_groups"]

        self.assertEqual(handbook_group["name"], "student_handbook_rag")
        self.assertEqual(handbook_group["total_files"], 1)
        self.assertEqual(handbook_group["total_chunks"], 1)
        self.assertEqual(handbook_group["files"][0]["display_name"], "handbook.md")
        self.assertTrue(handbook_group["files"][0]["is_upload_source"])

        self.assertEqual(policy_group["name"], "school_policy_rag")
        self.assertEqual(policy_group["files"][0]["source_label"], "congvanquyetdinh/policy.md")
        self.assertFalse(policy_group["files"][0]["is_upload_source"])

        self.assertEqual(faq_group["name"], "student_faq_rag")
        self.assertEqual(faq_group["total_files"], 1)
        self.assertEqual(faq_group["files"][0]["display_name"], "faq.md")

        self.assertNotIn("BOT_RULE", payload["chunks_by_file"])


if __name__ == "__main__":
    unittest.main()
