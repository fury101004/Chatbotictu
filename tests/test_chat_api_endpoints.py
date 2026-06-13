from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import main
from config.settings import settings
from models.chat import RAGResult, RetrievedChunk
from services.chat.chat_service import process_chat_message
from services.chat.memory_service import SESSION_MEMORY, clear_memory_store
from services.memory_store import stable_session_id


class ChatServicePipelineTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        clear_memory_store()

    async def test_process_chat_message_rewrites_follow_up_before_route_retrieval_and_generation(self) -> None:
        original = "thế còn khóa 2025-2026 thì sao?"
        rewritten = "Khóa 2025-2026 cần bao nhiêu tín chỉ để tốt nghiệp cử nhân?"
        rag_result = RAGResult(
            context_text="Chương trình đào tạo đại học (cử nhân) có khối lượng học tập tối thiểu 120 tín chỉ.",
            chunks=[
                RetrievedChunk(
                    document="Chương trình cử nhân tối thiểu 120 tín chỉ.",
                    metadata={"source": "student_handbooks/8.md", "score": 157},
                )
            ],
            mode="student_handbook_rag",
            sources=["student_handbooks/8.md"],
            chunks_used=1,
            rag_tool="student_handbook_rag",
            rag_route="router_handbook",
        )
        memory_store = SimpleNamespace(
            load=AsyncMock(
                return_value=[
                    {
                        "role": "user",
                        "content": "khóa 2024-2025 cần bao nhiêu tín chỉ để tốt nghiệp cử nhân?",
                    },
                    {"role": "model", "content": "Chương trình cử nhân cần 120 tín chỉ."},
                ]
            ),
            save=AsyncMock(),
        )
        eval_tracker = SimpleNamespace(log_response=AsyncMock())

        with (
            patch("services.chat.chat_service.get_default_memory_store", return_value=memory_store),
            patch("services.chat.chat_service.get_eval_tracker", return_value=eval_tracker),
            patch("services.chat.chat_service.route_rag_tool", return_value=("student_handbook_rag", "router_handbook")) as route_mock,
            patch("services.chat.chat_service.retrieve_tool_context", return_value=rag_result) as retrieval_mock,
            patch("services.chat.chat_service.chat_multilingual", return_value=("Cần tối thiểu 120 tín chỉ.", "local:test")) as chat_mock,
            patch("services.chat.chat_service.save_message", side_effect=[1, 2]) as save_mock,
            patch("services.chat.chat_service.append_retrieval_memory"),
            patch("services.content.knowledge_base_service.mark_chat_entry_pending"),
        ):
            result = await process_chat_message(
                original,
                session_id="follow-up-1",
                owner_username="Student@ICTU.edu.vn",
            )

        self.assertNotEqual(result["mode"], "ictu_scope_guard")
        memory_store.load.assert_awaited_once_with(
            stable_session_id(user_id="student@ictu.edu.vn", anonymous_id="follow-up-1")
        )
        route_mock.assert_called_once_with(rewritten)
        self.assertEqual(retrieval_mock.call_args.kwargs["message"], rewritten)
        self.assertEqual(chat_mock.call_args.kwargs["user_question"], rewritten)
        self.assertEqual(save_mock.call_args_list[0].args[:2], ("user", original))
        self.assertEqual(save_mock.call_args_list[0].kwargs["rewritten_question"], rewritten)
        self.assertEqual(eval_tracker.log_response.call_args.kwargs["query"], rewritten)
        saved_memory = memory_store.save.call_args.args[1]
        self.assertEqual(saved_memory[-2], {"role": "user", "content": rewritten})

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

    async def test_process_chat_message_answers_source_year_follow_up_from_retrieval_memory(self) -> None:
        SESSION_MEMORY["source-year-1"].append(
            {
                "query": "Khi nào sinh viên bị cảnh báo học tập?",
                "sources": [
                    "student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md",
                    "uploads/student_faq_rag/approved-chat-canh-bao-2025-2026.md",
                ],
            }
        )

        with (
            patch("services.chat.chat_service.route_rag_tool") as route_mock,
            patch("services.chat.chat_service.save_message", side_effect=[1, 2]),
        ):
            result = await process_chat_message(
                "phần này là của năm bao nhiêu",
                session_id="source-year-1",
            )

        self.assertEqual(result["intent"], "source_year_follow_up")
        self.assertEqual(result["llm_model"], "local:retrieval_memory")
        self.assertIn("2025-2026", result["response"])
        route_mock.assert_not_called()

    async def test_process_chat_message_answers_source_year_follow_up_after_new_session(self) -> None:
        memory_store = SimpleNamespace(
            load=AsyncMock(
                return_value=[
                    {
                        "role": "model",
                        "content": "Sinh viên bị cảnh báo học tập khi...",
                        "sources": ["student_handbooks/7. SO TAY SINH VIEN 2024-2025.md"],
                    }
                ]
            ),
            save=AsyncMock(),
        )

        with (
            patch("services.chat.chat_service.get_default_memory_store", return_value=memory_store),
            patch("services.chat.chat_service.route_rag_tool") as route_mock,
            patch("services.chat.chat_service.save_message", side_effect=[1, 2]),
        ):
            result = await process_chat_message(
                "nội dung trên thuộc năm học nào?",
                session_id="new-session",
                owner_username="student",
            )

        self.assertEqual(result["intent"], "source_year_follow_up")
        self.assertIn("2024-2025", result["response"])
        route_mock.assert_not_called()

    async def test_process_chat_message_answers_retake_improvement_question_from_handbook(self) -> None:
        question = "Học lại có được cải thiện điểm không?"
        eval_tracker = SimpleNamespace(log_response=AsyncMock())

        with (
            patch("services.rag.rag_service._route_retrieval_flow_by_llm", return_value=None),
            patch(
                "services.chat.chat_service.chat_multilingual",
                return_value=("Có, sinh viên được học lại để cải thiện điểm C hoặc D.", "local:test"),
            ) as chat_mock,
            patch("services.chat.chat_service.save_message", side_effect=[1, 2]),
            patch("services.chat.chat_service.append_retrieval_memory"),
            patch("services.content.knowledge_base_service.mark_chat_entry_pending"),
            patch("services.chat.chat_service.get_eval_tracker", return_value=eval_tracker),
        ):
            result = await process_chat_message(question, session_id="retake-improvement-1")

        self.assertFalse(result["needs_clarification"])
        self.assertEqual(result["rag_tool"], "student_handbook_rag")
        self.assertEqual(result["sources"], ["student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md"])
        self.assertEqual(
            result["source_details"],
            [
                {
                    "source": "student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md",
                    "label": "Sổ tay sinh viên 2025-2026 (hỏi đáp trích xuất)",
                }
            ],
        )
        context_text = chat_mock.call_args.kwargs["context_text"]
        self.assertIn("được phép đăng ký học lại để cải thiện điểm", context_text)
        self.assertIn("điểm C hoặc D", context_text)


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
            patch(
                "services.chat.chat_service.chat_multilingual",
                return_value=(
                    "Dieu kien tot nghiep can du tin chi.\n\n"
                    "---\n"
                    "📚 Nguồn tham khảo:\n"
                    "- student_handbooks/2025.md",
                    "local:test",
                ),
            ),
            patch("services.chat.chat_service.save_message", side_effect=[1, 2]),
            patch("services.content.knowledge_base_service.mark_chat_entry_pending") as pending_mock,
            patch("services.chat.chat_service.append_retrieval_memory"),
        ):
            result = await process_chat_message("Dieu kien tot nghiep la gi?", session_id="review-1")

        self.assertEqual(result["qa_review_status"], "pending")
        self.assertEqual(result["qa_review_entry_id"], "chat::review-1::2")
        self.assertEqual(result["response"], "Dieu kien tot nghiep can du tin chi.")
        self.assertEqual(result["sources"], ["student_handbooks/2025.md"])
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

    def test_deployment_status_routes_are_available(self) -> None:
        client = TestClient(main.app)

        with (
            patch("views.api_view.embedding_backend_ready", return_value=True),
            patch("views.api_view.get_model", return_value=SimpleNamespace(label="groq:test-model")),
        ):
            v1_response = client.get("/api/v1/deployment/status")
            api_response = client.get("/api/deployment/status")

        self.assertEqual(v1_response.status_code, 200)
        self.assertEqual(api_response.status_code, 200)
        payload = v1_response.json()
        self.assertEqual(payload["app_name"], settings.APP_NAME)
        self.assertIn(payload["status"], {"ready", "degraded"})
        self.assertEqual(payload["checks"]["llm_configured"], True)
        self.assertEqual(payload["checks"]["embedding_backend_ready"], True)
        self.assertIn("data_dir_writable", payload["checks"])

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
        self.assertIsNone(payload["source_details"])


if __name__ == "__main__":
    unittest.main()
