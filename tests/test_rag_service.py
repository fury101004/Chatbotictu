import unittest
from unittest import mock

from app.services import rag_service
from app.services.llm_service import LLMInvocationError


class RagServiceTests(unittest.TestCase):
    def _state(self):
        return {
            "question": "BHYT kỳ này đóng khi nào?",
            "history": [],
            "memory": "",
            "route": "faq",
            "documents": [],
            "context": "Tài liệu mẫu",
            "answer": "",
            "sources": [],
        }

    def test_answer_node_returns_dev_safe_detail_when_debug_enabled(self):
        llm_error = LLMInvocationError(
            provider="gemini",
            requested_model="gemini-2.5-flash",
            attempted_models=("gemini-2.5-flash", "gemini-1.5-flash"),
            status_code=404,
            detail="Requested model was not found for key AIzaSyExampleLeakToken1234567890.",
        )

        with mock.patch("app.services.rag_service.invoke_llm", side_effect=llm_error), mock.patch.object(
            rag_service, "APP_DEBUG", True
        ):
            result = rag_service.answer_node(self._state())

        self.assertIn("GEMINI", result["answer"])
        self.assertIn("Chi tiết dev:", result["answer"])
        self.assertIn("gemini-1.5-flash", result["answer"])
        self.assertNotIn("AIzaSyExampleLeakToken1234567890", result["answer"])

    def test_answer_node_hides_dev_detail_when_debug_disabled(self):
        llm_error = LLMInvocationError(
            provider="gemini",
            requested_model="gemini-2.5-flash",
            attempted_models=("gemini-2.5-flash",),
            status_code=403,
            detail="Permission denied for AIzaSyExampleLeakToken1234567890.",
        )

        with mock.patch("app.services.rag_service.invoke_llm", side_effect=llm_error), mock.patch.object(
            rag_service, "APP_DEBUG", False
        ):
            result = rag_service.answer_node(self._state())

        self.assertIn("GEMINI", result["answer"])
        self.assertNotIn("Chi tiết dev:", result["answer"])
        self.assertNotIn("AIzaSyExampleLeakToken1234567890", result["answer"])


if __name__ == "__main__":
    unittest.main()
