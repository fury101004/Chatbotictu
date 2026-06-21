from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from models.chat import RAGResult, RetrievedChunk
from services.chat.chat_service import _normalize_input, process_chat_message


class ChatClarificationTests(unittest.IsolatedAsyncioTestCase):
    def test_malformed_timeframe_reply_keeps_the_pending_question(self) -> None:
        history = [
            {"role": "user", "content": "Muốn xét học bổng cần điều kiện gì?"},
            {
                "role": "assistant",
                "content": "Bạn muốn hỏi cho năm học hoặc đợt nào để mình tra đúng tài liệu?",
            },
        ]

        invalid = _normalize_input(
            {
                "message": "2-25-2-26",
                "session_id": "clarify-invalid-year",
                "persistent_memory": history,
            }
        )
        self.assertTrue(invalid["handled"])
        self.assertEqual(invalid["llm_model"], "local:invalid_timeframe_clarification")
        self.assertIn("2025-2026", invalid["response"])

        corrected = _normalize_input(
            {
                "message": "2025-2026",
                "session_id": "clarify-invalid-year",
                "persistent_memory": [
                    *history,
                    {"role": "user", "content": "2-25-2-26"},
                    {"role": "model", "content": invalid["response"]},
                ],
            }
        )
        self.assertFalse(corrected["handled"])
        self.assertEqual(
            corrected["message"],
            "Về 2025-2026, muốn xét học bổng cần điều kiện gì?",
        )

    async def test_process_chat_message_does_not_force_clarification_when_sources_exist(self) -> None:
        rich_result = RAGResult(
            context_text="Sinh vien phai dap ung du dieu kien ve tin chi va hoc phan.",
            chunks=[
                RetrievedChunk(
                    document="Sinh vien phai hoan thanh du tin chi.",
                    metadata={"source": "student_handbooks/2025.md"},
                ),
                RetrievedChunk(
                    document="Quy che xet tot nghiep ap dung theo nam hoc.",
                    metadata={"source": "student_handbooks/2026.md"},
                ),
            ],
            mode="student_handbook_rag",
            sources=["student_handbooks/2025.md", "student_handbooks/2026.md"],
            chunks_used=2,
            rag_tool="student_handbook_rag",
            rag_route="router_handbook",
        )
        memory_store = SimpleNamespace(load=AsyncMock(return_value=[]), save=AsyncMock())
        eval_tracker = SimpleNamespace(log_response=AsyncMock())

        with (
            patch("services.chat.chat_service.get_default_memory_store", return_value=memory_store),
            patch("services.chat.chat_service.get_eval_tracker", return_value=eval_tracker),
            patch("services.chat.chat_service.route_rag_tool", return_value=("student_handbook_rag", "router_handbook")),
            patch("services.chat.chat_service.retrieve_tool_context", return_value=rich_result),
            patch(
                "services.chat.chat_service.chat_multilingual",
                return_value=("Sinh vien can dap ung du so tin chi va cac dieu kien xet tot nghiep.", "local:test"),
            ) as chat_mock,
            patch("services.chat.chat_service.save_message", side_effect=[1, 2]),
            patch("services.chat.chat_service.append_retrieval_memory"),
            patch("services.content.knowledge_base_service.approve_chat_entry"),
            patch("services.content.knowledge_base_service.mark_chat_entry_pending"),
        ):
            result = await process_chat_message("Điều kiện tốt nghiệp là gì?", session_id="clarify-skip-1")

        self.assertFalse(result["needs_clarification"])
        self.assertNotEqual(result["llm_model"], "local:clarification")
        self.assertEqual(chat_mock.call_args.kwargs["user_question"], "Điều kiện tốt nghiệp là gì?")


if __name__ == "__main__":
    unittest.main()
