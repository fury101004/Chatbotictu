from __future__ import annotations

import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import UploadFile

import services.vector_store_service as vector_store_service
from services.document_service import upload_markdown_files
from services.rag_service import (
    CorpusDocument,
    RETRIEVAL_LOCAL_DATA,
    RETRIEVAL_LOCAL_FIRST,
    RETRIEVAL_WEB_FIRST,
    RETRIEVAL_WEB_SEARCH,
    RetrievalFlowPlan,
    _extract_relevant_snippet,
    _normalize_for_match,
    _search_documents,
    _tokenize,
    retrieve_tool_context,
    route_rag_tool,
    route_retrieval_flow,
)
from models.chat import RAGResult


class UploadFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_saves_file_even_when_indexing_fails(self) -> None:
        with tempfile.TemporaryDirectory(dir="E:\\new-test") as temp_dir:
            upload_dir = Path(temp_dir)
            upload = UploadFile(filename="guide.md", file=BytesIO(b"# Guide\n\nNoi dung"))

            with (
                patch("services.document_service.get_tool_upload_dir", return_value=upload_dir),
                patch("services.document_service.add_documents", side_effect=RuntimeError("vector unavailable")),
                patch("services.document_service.get_uploaded_files", return_value=[]),
                patch("services.document_service.add_uploaded_file") as add_uploaded_file_mock,
                patch("services.document_service.clear_rag_corpus_cache") as clear_cache_mock,
            ):
                result = await upload_markdown_files(files=[upload], tool_name="student_faq_rag")

            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["added"], 1)
            self.assertEqual(result["indexed"], 0)
            self.assertEqual(result["warnings"], 1)
            self.assertTrue((upload_dir / "guide.md").exists())
            add_uploaded_file_mock.assert_called_once()
            clear_cache_mock.assert_called_once()

    async def test_upload_indexes_file_when_embedding_backend_is_ready(self) -> None:
        with tempfile.TemporaryDirectory(dir="E:\\new-test") as temp_dir:
            upload_dir = Path(temp_dir)
            upload = UploadFile(filename="guide.md", file=BytesIO(b"# Guide\n\nNoi dung"))

            with (
                patch("services.document_service.get_tool_upload_dir", return_value=upload_dir),
                patch("services.document_service.embedding_backend_ready", return_value=True),
                patch("services.document_service.add_documents") as add_documents_mock,
                patch("services.document_service.get_uploaded_files", return_value=[]),
                patch("services.document_service.add_uploaded_file"),
                patch("services.document_service.clear_rag_corpus_cache"),
            ):
                result = await upload_markdown_files(files=[upload], tool_name="student_faq_rag")

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["indexed"], 1)
            self.assertEqual(result["warnings"], 0)
            add_documents_mock.assert_called_once_with(
                file_content="# Guide\n\nNoi dung",
                filename="guide.md",
                source_name="uploads/student_faq_rag/guide.md",
                tool_name="student_faq_rag",
            )


class EmbeddingBackendTests(unittest.TestCase):
    def tearDown(self) -> None:
        vector_store_service.ef = None
        vector_store_service.embedding_backend_ready.cache_clear()

    def test_embedding_backend_ready_when_local_model_exists_without_network(self) -> None:
        with (
            patch("services.vector_store_service._resolve_local_embedding_model_path", return_value=Path("C:/models/local-embed")),
            patch("services.vector_store_service.socket.create_connection", side_effect=OSError("blocked")),
        ):
            vector_store_service.embedding_backend_ready.cache_clear()
            self.assertTrue(vector_store_service.embedding_backend_ready())

    def test_get_embedding_function_forces_offline_mode_with_local_model(self) -> None:
        with (
            patch("services.vector_store_service._resolve_local_embedding_model_path", return_value=Path("C:/models/local-embed")),
            patch("services.vector_store_service.embedding_functions.SentenceTransformerEmbeddingFunction") as factory,
            patch.dict(os.environ, {}, clear=True),
        ):
            vector_store_service.ef = None
            factory.return_value = object()

            result = vector_store_service.get_embedding_function()

            self.assertEqual(os.environ["HF_HUB_OFFLINE"], "1")
            self.assertEqual(os.environ["TRANSFORMERS_OFFLINE"], "1")

        self.assertIs(result, factory.return_value)
        factory.assert_called_once_with(
            model_name=str(Path("C:/models/local-embed")),
            local_files_only=True,
        )


class RagRouterTests(unittest.TestCase):
    def test_keyword_router_is_used_when_llm_is_unavailable(self) -> None:
        with patch("services.rag_service.get_model", return_value=None):
            tool_name, route_name = route_rag_tool("quy che hoc phi")

        self.assertEqual(tool_name, "school_policy_rag")
        self.assertTrue(route_name.startswith("router_keyword_score:"))

    def test_strong_handbook_keyword_route_skips_llm_router(self) -> None:
        question = "Điều kiện đạt danh hiệu sinh viên Khá, Giỏi, Xuất sắc là gì?"

        with patch("services.rag_service._route_rag_tool_by_llm") as llm_router:
            tool_name, route_name = route_rag_tool(question)

        self.assertEqual(tool_name, "student_handbook_rag")
        self.assertTrue(route_name.startswith("router_keyword_score:"))
        llm_router.assert_not_called()


class RetrievalFlowPlannerTests(unittest.TestCase):
    def test_llm_planner_can_choose_web_search_before_retrieval(self) -> None:
        with (
            patch("services.rag_service.get_model", return_value=SimpleNamespace(label="planner-model")),
            patch("services.rag_service._llm_router_network_available", return_value=True),
            patch(
                "services.rag_service.invoke_json_prompt_chain",
                return_value=(
                    {
                        "source": "web_search",
                        "priority": "web_first",
                        "reason": "Thong bao moi can web",
                        "confidence": 0.91,
                    },
                    '{"source":"web_search","priority":"web_first","reason":"Thong bao moi can web","confidence":0.91}',
                    "planner-model",
                ),
            ) as chain_mock,
        ):
            plan = route_retrieval_flow("ICTU có thông báo mới nhất gì hôm nay?", "student_faq_rag")

        self.assertEqual(plan.source, RETRIEVAL_WEB_SEARCH)
        self.assertEqual(plan.priority, RETRIEVAL_WEB_FIRST)
        self.assertTrue(plan.route.startswith("flow_llm:web_search:web_first"))
        prompt_template = chain_mock.call_args.args[0]
        prompt_input = chain_mock.call_args.args[1]
        self.assertEqual(prompt_input["current_tool"], "student_faq_rag")
        self.assertIn("local_data", prompt_template.messages[1].prompt.template)
        self.assertIn("web_search", prompt_template.messages[1].prompt.template)
        self.assertIn("hybrid", prompt_template.messages[1].prompt.template)

    def test_flow_falls_back_to_web_search_for_realtime_question_without_llm(self) -> None:
        with patch("services.rag_service.get_model", return_value=None):
            plan = route_retrieval_flow("ICTU có thông báo mới nhất gì hôm nay?", "student_faq_rag")

        self.assertEqual(plan.source, RETRIEVAL_WEB_SEARCH)
        self.assertEqual(plan.priority, RETRIEVAL_WEB_FIRST)

    def test_flow_falls_back_to_local_data_for_stable_handbook_question_without_llm(self) -> None:
        with patch("services.rag_service.get_model", return_value=None):
            plan = route_retrieval_flow("Điều kiện đạt danh hiệu sinh viên Khá, Giỏi, Xuất sắc là gì?", "student_handbook_rag")

        self.assertEqual(plan.source, RETRIEVAL_LOCAL_DATA)
        self.assertEqual(plan.priority, RETRIEVAL_LOCAL_FIRST)

    def test_web_search_plan_returns_web_result_before_local_lookup(self) -> None:
        plan = RetrievalFlowPlan(
            source=RETRIEVAL_WEB_SEARCH,
            priority=RETRIEVAL_WEB_FIRST,
            reason="Thong tin moi",
            confidence=0.9,
            route="flow_test:web",
        )
        web_result = RAGResult(
            context_text="Thong bao moi tu web ICTU",
            mode="web_search",
            sources=["https://ictu.edu.vn/thong-bao"],
            chunks_used=1,
            rag_tool="student_faq_rag",
            rag_route="router_test|flow_test:web",
        )

        with (
            patch("services.rag_service.is_ictu_related_query", return_value=True),
            patch("services.rag_service._build_planned_web_result", return_value=web_result),
            patch("services.rag_service._load_tool_corpus") as load_corpus_mock,
        ):
            result = retrieve_tool_context(
                "ICTU có thông báo mới nhất gì hôm nay?",
                "test-web-plan",
                "student_faq_rag",
                "router_test",
                retrieval_plan=plan,
            )

        self.assertIs(result, web_result)
        load_corpus_mock.assert_not_called()


class RagLexicalQaTests(unittest.TestCase):
    def _doc(self, name: str, text: str) -> CorpusDocument:
        title = Path(name).stem
        source = f"Sổ tay sinh viên các năm/{name}"
        return CorpusDocument(
            path=Path(name),
            source=source,
            title=title,
            text=text,
            text_lower=text.casefold(),
            normalized_text=_normalize_for_match(text),
            normalized_title=_normalize_for_match(title),
            normalized_source=_normalize_for_match(source),
            token_set=frozenset(_tokenize(f"{title}\n{source}\n{text}")),
        )

    def test_exact_question_block_is_extracted_from_question_file(self) -> None:
        text = """
# Question Set

**Question:** Tài liệu Sổ tay sinh viên dùng để làm gì?
**Answer:** Tài liệu dùng để cung cấp thông tin chung cho sinh viên.

## Question 14

**Question:** Điều kiện đạt danh hiệu sinh viên Khá, Giỏi, Xuất sắc là gì?
**Answer:** Sinh viên Khá cần kết quả học tập từ 2,50 đến 3,19 theo thang điểm 4 và rèn luyện từ khá trở lên; sinh viên Giỏi cần kết quả học tập từ 3,20 đến 3,59 và rèn luyện từ tốt trở lên; sinh viên Xuất sắc cần kết quả học tập từ 3,60 trở lên và rèn luyện xuất sắc.
"""
        question = "Điều kiện đạt danh hiệu sinh viên Khá, Giỏi, Xuất sắc là gì?"
        snippet = _extract_relevant_snippet(self._doc("handbook.questions.md", text), question, _tokenize(question))

        self.assertIn("2,50 đến 3,19", snippet)
        self.assertIn("3,60 trở lên", snippet)
        self.assertNotIn("Tài liệu dùng để cung cấp", snippet)

    def test_question_files_are_ranked_ahead_of_raw_context_for_exact_qa(self) -> None:
        question = "Điều kiện đạt danh hiệu sinh viên Khá, Giỏi, Xuất sắc là gì?"
        raw_doc = self._doc(
            "handbook.md",
            """
### Q14. Điều kiện đạt danh hiệu sinh viên Khá, Giỏi, Xuất sắc là gì?

Sinh viên Khá cần kết quả học tập từ 2,50 đến 3,19.
""",
        )
        question_doc = self._doc(
            "handbook.questions.md",
            """
**Question:** Điều kiện đạt danh hiệu sinh viên Khá, Giỏi, Xuất sắc là gì?
**Answer:** Sinh viên Khá cần kết quả học tập từ 2,50 đến 3,19; sinh viên Giỏi cần từ 3,20 đến 3,59; sinh viên Xuất sắc cần từ 3,60 trở lên.
""",
        )

        matches = _search_documents((raw_doc, question_doc), question, limit=2)

        self.assertEqual(matches[0][1].path.name, "handbook.questions.md")


if __name__ == "__main__":
    unittest.main()
