from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import main
from config.settings import settings
from models.chat import RAGResult, RetrievedChunk
from services.chat.chat_service import process_chat_message


class ChatServicePipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_chat_message_asks_for_clarification_when_question_lacks_required_scope(self) -> None:
        empty_result = RAGResult(
            context_text="Thông tin đang được cập nhật.",
            chunks=[],
            mode="lexical_fallback_empty",
            sources=[],
            chunks_used=0,
            rag_tool="school_policy_rag",
            rag_route="router_policy",
        )

        with (
            patch("services.chat.chat_service.route_rag_tool", return_value=("school_policy_rag", "router_policy")),
            patch("services.chat.chat_service.retrieve_tool_context", return_value=empty_result),
            patch("services.chat.chat_service.save_message"),
        ):
            result = await process_chat_message("Học phí là bao nhiêu?", session_id="clarify-1")

        self.assertTrue(result["needs_clarification"])
        self.assertEqual(result["llm_model"], "local:clarification")
        self.assertIn("năm học", result["response"])

    async def test_process_chat_message_returns_safe_fallback_when_no_context_is_found(self) -> None:
        empty_result = RAGResult(
            context_text="Thông tin đang được cập nhật.",
            chunks=[],
            mode="lexical_fallback_empty",
            sources=[],
            chunks_used=0,
            rag_tool="student_faq_rag",
            rag_route="router_faq",
        )

        with (
            patch("services.chat.chat_service.route_rag_tool", return_value=("student_faq_rag", "router_faq")),
            patch("services.chat.chat_service.retrieve_tool_context", return_value=empty_result),
            patch("services.chat.chat_service.save_message"),
        ):
            result = await process_chat_message("Email phòng ban nào xử lý việc đặc biệt này?", session_id="fallback-1")

        self.assertFalse(result["needs_clarification"])
        self.assertEqual(result["llm_model"], "local:knowledge_base_fallback")
        self.assertIn("Knowledge Base", result["response"])

    async def test_process_chat_message_returns_local_greeting_intent(self) -> None:
        with patch("services.chat.chat_service.save_message"):
            result = await process_chat_message("Xin chào", session_id="greeting-1")

        self.assertEqual(result["intent"], "greeting")
        self.assertEqual(result["llm_model"], "local:quick_reply")
        self.assertTrue(result["response"])


    async def test_process_chat_message_queues_source_grounded_answer_for_review(self) -> None:
        rag_result = RAGResult(
            context_text="Thong tin dieu kien tot nghiep trong so tay sinh vien.",
            chunks=[
                RetrievedChunk(
                    document="Dieu kien tot nghiep",
                    metadata={"path": "student_handbooks/2025.md", "id": "chunk-1"},
                )
            ],
            mode="hybrid_search",
            sources=["student_handbooks/2025.md"],
            chunks_used=1,
            rag_tool="student_handbook_rag",
            rag_route="router_handbook",
        )

        with (
            patch("services.chat.chat_service.route_rag_tool", return_value=("student_handbook_rag", "router_handbook")),
            patch("services.chat.chat_service.retrieve_tool_context", return_value=rag_result),
            patch("services.chat.chat_service.chat_multilingual", return_value=("Dieu kien tot nghiep can du tin chi.", "local:test")),
            patch("services.chat.chat_service.save_message", side_effect=[1, 2]),
            patch("services.content.knowledge_base_service.mark_chat_entry_pending") as pending_mock,
            patch("services.chat.chat_service.append_retrieval_memory"),
        ):
            result = await process_chat_message("Dieu kien tot nghiep la gi?", session_id="review-1")

        self.assertEqual(result["qa_review_status"], "pending")
        self.assertEqual(result["qa_review_entry_id"], "chat::review-1::2")
        pending_mock.assert_called_once()


class ApiEndpointTests(unittest.TestCase):
    def _get_token(self, client: TestClient) -> str:
        response = client.post("/api/auth/token", data={"partner_key": settings.PARTNER_API_KEY})
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    def test_health_routes_are_available(self) -> None:
        client = TestClient(main.app)

        with (
            patch("views.api_view.embedding_backend_ready", return_value=True),
            patch("views.api_view.get_model", return_value=SimpleNamespace(label="groq:test-model")),
        ):
            root_response = client.get("/health")
            api_response = client.get("/api/health")

        self.assertEqual(root_response.status_code, 200)
        self.assertEqual(api_response.status_code, 200)
        self.assertEqual(root_response.json()["status"], "healthy")
        self.assertIn("llm_configured", api_response.json())

    def test_api_chat_alias_returns_expected_payload(self) -> None:
        client = TestClient(main.app)
        token = self._get_token(client)

        mock_chat = AsyncMock(
            return_value={
                "response": "Thong tin hoc phi nam 2025-2026.",
                "sources": ["uploads/student_faq_rag/hoc_phi.md"],
                "mode": "student_faq_rag",
                "chunks_used": 2,
                "language": "vi",
                "rag_tool": "student_faq_rag",
                "rag_route": "router_faq",
                "llm_model": "local:test",
                "intent": "rag",
                "needs_clarification": False,
                "response_time_ms": 12,
            }
        )

        with patch("controllers.api_controller.process_chat_message", mock_chat):
            response = client.post(
                "/api/chat",
                headers={"Authorization": f"Bearer {token}"},
                json={"message": "Hoc phi la bao nhieu?", "session_id": "api-chat-1"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["response"], "Thong tin hoc phi nam 2025-2026.")
        self.assertEqual(payload["session_id"], "api-chat-1")
        self.assertEqual(payload["response_time_ms"], 12)
        self.assertEqual(payload["sources"], ["uploads/student_faq_rag/hoc_phi.md"])


if __name__ == "__main__":
    unittest.main()
