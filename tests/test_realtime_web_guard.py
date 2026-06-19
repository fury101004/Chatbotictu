from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from models.chat import RAGResult, RetrievedChunk
from services.chat.chat_service import process_chat_message
from services.chat.memory_service import clear_memory_store


class RealtimeWebGuardTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        clear_memory_store()

    async def test_realtime_query_returns_web_search_empty_even_with_local_context(self) -> None:
        local_result = RAGResult(
            context_text="ThĂ´ng bĂ¡o phá»‘i há»£p lĂ m viá»‡c sáº¯p tá»›i.",
            chunks=[
                RetrievedChunk(
                    document="ThĂ´ng bĂ¡o phá»‘i há»£p lĂ m viá»‡c sáº¯p tá»›i.",
                    metadata={"source": "student_faqs/news.md"},
                )
            ],
            mode="student_faq_rag",
            sources=["student_faqs/news.md"],
            chunks_used=1,
            rag_tool="general_ictu_rag",
            rag_route="router_general",
        )

        with (
            patch("services.chat.chat_service.route_rag_tool", return_value=("general_ictu_rag", "router_general")),
            patch("services.chat.chat_service.retrieve_general_context", return_value=local_result),
            patch("services.chat.chat_service.chat_multilingual") as chat_mock,
            patch("services.chat.chat_service.save_message"),
            patch("services.chat.chat_service.get_default_memory_store") as memory_store_mock,
            patch("services.chat.chat_service.get_eval_tracker") as eval_tracker_mock,
        ):
            memory_store_mock.return_value = SimpleNamespace(
                load=AsyncMock(return_value=[]),
                save=AsyncMock(),
            )
            eval_tracker_mock.return_value = SimpleNamespace(log_response=AsyncMock())

            result = await process_chat_message("ICTU hôm nay có j mới?", session_id="web-force-empty-1")

        self.assertEqual(result["llm_model"], "local:web_search_empty")
        self.assertEqual(result["mode"], "web_search_empty")
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["chunks_used"], 0)
        self.assertNotIn("source_details", result)
        self.assertIn("nguồn web ICTU", result["response"])
        chat_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
