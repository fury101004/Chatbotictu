from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.knowledge_base_service import (
    ChatKnowledgeEntry,
    VectorKnowledgeEntry,
    _pair_chat_rows,
    approve_chat_entry,
    get_knowledge_base_payload,
)


class ChatKnowledgePairingTests(unittest.TestCase):
    def test_pair_chat_rows_matches_user_and_bot_within_same_session(self) -> None:
        rows = [
            {"id": 1, "role": "user", "content": "Hoc phi nam 2024 la gi?", "timestamp": "2026-04-09 10:00:00", "session_id": "alpha"},
            {"id": 2, "role": "bot", "content": "Thong tin hoc phi dang duoc cap nhat.", "timestamp": "2026-04-09 10:00:05", "session_id": "alpha"},
            {"id": 3, "role": "user", "content": "Email sinh vien o dau?", "timestamp": "2026-04-09 10:01:00", "session_id": "beta"},
            {"id": 4, "role": "user", "content": "So tay 2021-2022 co gi?", "timestamp": "2026-04-09 10:01:30", "session_id": "alpha"},
            {"id": 5, "role": "assistant", "content": "So tay 2021-2022 co thong tin tong quan ve nha truong.", "timestamp": "2026-04-09 10:01:40", "session_id": "alpha"},
            {"id": 6, "role": "bot", "content": "Email sinh vien duoc cap qua he thong nha truong.", "timestamp": "2026-04-09 10:02:00", "session_id": "beta"},
        ]

        pairs = _pair_chat_rows(rows)

        self.assertEqual(len(pairs), 3)
        self.assertEqual(pairs[0].session_id, "beta")
        self.assertEqual(pairs[0].question, "Email sinh vien o dau?")
        self.assertIn("he thong nha truong", pairs[0].answer)
        self.assertEqual(pairs[1].session_id, "alpha")
        self.assertEqual(pairs[1].question, "So tay 2021-2022 co gi?")
        self.assertEqual(pairs[2].question, "Hoc phi nam 2024 la gi?")


class KnowledgeBasePayloadTests(unittest.TestCase):
    def test_payload_merges_vector_and_chat_sources_in_search_results(self) -> None:
        vector_entries = [
            VectorKnowledgeEntry(
                source="congvanquyetdinh/hoc_phi.md",
                display_name="hoc_phi.md",
                tool_name="school_policy_rag",
                tool_label="Quy dinh va chinh sach",
                chunk_count=3,
                titles=["Hoc phi"],
                preview="Thong tin hoc phi va mien giam hoc phi.",
                content="Thong tin hoc phi va mien giam hoc phi cho sinh vien nam 2024.",
            )
        ]
        chat_rows = [
            {"id": 1, "role": "user", "content": "Hoc phi dong khi nao?", "timestamp": "2026-04-09 09:00:00", "session_id": "s1"},
            {"id": 2, "role": "bot", "content": "Hoc phi duoc thong bao theo tung dot trong nam hoc.", "timestamp": "2026-04-09 09:00:08", "session_id": "s1"},
        ]

        with (
            patch("services.knowledge_base_service._load_vector_entries", return_value=(vector_entries, 3)),
            patch("services.knowledge_base_service._fetch_chat_rows", return_value=chat_rows),
            patch("services.knowledge_base_service.get_approved_chat_entry_ids", return_value=set()),
            patch("services.knowledge_base_service.get_approved_chat_qas", return_value=[]),
        ):
            payload = get_knowledge_base_payload(query="hoc phi", limit=10)

        self.assertEqual(payload["summary"]["vector_files"], 1)
        self.assertEqual(payload["summary"]["chat_pairs"], 1)
        self.assertEqual(payload["summary"]["matched_results"], 2)
        self.assertEqual({item["kind"] for item in payload["search_results"]}, {"vector", "chatbot"})

    def test_payload_blocks_non_ictu_search_query(self) -> None:
        vector_entries = [
            VectorKnowledgeEntry(
                source="congvanquyetdinh/hoc_phi.md",
                display_name="hoc_phi.md",
                tool_name="school_policy_rag",
                tool_label="Quy dinh va chinh sach",
                chunk_count=3,
                titles=["Hoc phi"],
                preview="Thong tin hoc phi va mien giam hoc phi.",
                content="Thong tin hoc phi va mien giam hoc phi cho sinh vien nam 2024.",
            )
        ]

        with (
            patch("services.knowledge_base_service._load_vector_entries", return_value=(vector_entries, 3)),
            patch("services.knowledge_base_service._fetch_chat_rows", return_value=[]),
            patch("services.knowledge_base_service.get_approved_chat_entry_ids", return_value=set()),
            patch("services.knowledge_base_service.get_approved_chat_qas", return_value=[]),
        ):
            payload = get_knowledge_base_payload(query="thoi tiet Ha Noi hom nay", limit=10)

        self.assertEqual(payload["summary"]["matched_results"], 0)
        self.assertEqual(payload["search_results"], [])
        self.assertTrue(any("ngoài phạm vi ICTU" in warning for warning in payload["warnings"]))


class ApproveChatEntryTests(unittest.TestCase):
    def test_approve_chat_entry_writes_markdown_and_indexes_vector(self) -> None:
        entry = ChatKnowledgeEntry(
            entry_id="chat::s1::2",
            question_row_id=1,
            answer_row_id=2,
            session_id="s1",
            question="Hoc phi dong khi nao?",
            answer="Hoc phi duoc thong bao theo tung dot trong nam hoc.",
            timestamp="2026-04-09 09:00:08",
            time_label="09/04 09:00",
            preview="Hoc phi duoc thong bao theo tung dot trong nam hoc.",
            content="Q: Hoc phi dong khi nao?\nA: Hoc phi duoc thong bao theo tung dot trong nam hoc.",
        )

        with tempfile.TemporaryDirectory(dir="E:\\new-test") as temp_dir:
            upload_dir = Path(temp_dir)
            with (
                patch("services.knowledge_base_service.get_chat_entry_by_id", return_value=entry),
                patch("services.knowledge_base_service.get_tool_upload_dir", return_value=upload_dir),
                patch("services.knowledge_base_service.embedding_backend_ready", return_value=True),
                patch("services.knowledge_base_service.add_documents") as add_documents_mock,
                patch("services.knowledge_base_service.upsert_approved_chat_qa") as upsert_mock,
                patch("services.knowledge_base_service.clear_rag_corpus_cache") as clear_cache_mock,
            ):
                result = approve_chat_entry(entry_id=entry.entry_id)

            self.assertTrue(result["indexed"])
            self.assertTrue(Path(result["storage_path"]).exists())
            add_documents_mock.assert_called_once()
            upsert_mock.assert_called_once()
            clear_cache_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
