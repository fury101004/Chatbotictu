from __future__ import annotations

import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import UploadFile

from pipelines.retrieval_pipeline import build_retrieval_query, query_is_in_ictu_scope
import services.vector.vector_store_service as vector_store_service
from services.content.document_service import upload_markdown_files
from services.rag.rag_service import (
    CorpusDocument,
    RETRIEVAL_LOCAL_DATA,
    RETRIEVAL_LOCAL_FIRST,
    RETRIEVAL_WEB_FIRST,
    RETRIEVAL_WEB_SEARCH,
    RetrievalFlowPlan,
    _extract_relevant_snippet,
    _load_tool_corpus,
    _normalize_for_match,
    _search_documents,
    _tokenize,
    retrieve_tool_context,
    route_rag_tool,
    route_retrieval_flow,
)
from services.rag.rag_prompts import _RAW_TEXT_PROMPT, _build_rag_router_prompt, _build_retrieval_flow_prompt
from models.chat import RAGResult


class UploadFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_saves_file_even_when_indexing_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            upload_dir = Path(temp_dir)
            upload = UploadFile(filename="guide.md", file=BytesIO(b"# Guide\n\nNoi dung"))

            with (
                patch("services.content.document_service.get_tool_upload_dir", return_value=upload_dir),
                patch("services.content.document_service.add_documents", side_effect=RuntimeError("vector unavailable")),
                patch("services.content.document_service.get_uploaded_files", return_value=[]),
                patch("services.content.document_service.add_uploaded_file") as add_uploaded_file_mock,
                patch("services.content.document_service.clear_rag_corpus_cache") as clear_cache_mock,
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
        with tempfile.TemporaryDirectory() as temp_dir:
            upload_dir = Path(temp_dir)
            upload = UploadFile(filename="guide.md", file=BytesIO(b"# Guide\n\nNoi dung"))

            with (
                patch("services.content.document_service.get_tool_upload_dir", return_value=upload_dir),
                patch("services.content.document_service.embedding_backend_ready", return_value=True),
                patch("services.content.document_service.add_documents") as add_documents_mock,
                patch("services.content.document_service.get_uploaded_files", return_value=[]),
                patch("services.content.document_service.add_uploaded_file"),
                patch("services.content.document_service.clear_rag_corpus_cache"),
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
            patch("services.vector.vector_store_service._resolve_local_embedding_model_path", return_value=Path("local-embed-cache")),
            patch("services.vector.vector_store_service.socket.create_connection", side_effect=OSError("blocked")),
        ):
            vector_store_service.embedding_backend_ready.cache_clear()
            self.assertTrue(vector_store_service.embedding_backend_ready())

    def test_get_embedding_function_forces_offline_mode_with_local_model(self) -> None:
        with (
            patch("services.vector.vector_store_service._resolve_local_embedding_model_path", return_value=Path("local-embed-cache")),
            patch("services.vector.vector_store_service.embedding_functions.SentenceTransformerEmbeddingFunction") as factory,
            patch.dict(os.environ, {}, clear=True),
        ):
            vector_store_service.ef = None
            factory.return_value = object()

            result = vector_store_service.get_embedding_function()

            self.assertEqual(os.environ["HF_HUB_OFFLINE"], "1")
            self.assertEqual(os.environ["TRANSFORMERS_OFFLINE"], "1")

        self.assertIs(result, factory.return_value)
        factory.assert_called_once_with(
            model_name=str(Path("local-embed-cache")),
            local_files_only=True,
        )


class RagRouterTests(unittest.TestCase):
    def test_rag_router_prompt_with_json_example_formats_as_plain_text(self) -> None:
        prompt_text = _build_rag_router_prompt("hoc phi ICTU nam nay la bao nhieu?")

        formatted = _RAW_TEXT_PROMPT.invoke({"prompt": prompt_text})

        self.assertEqual(_RAW_TEXT_PROMPT.input_variables, ["prompt"])
        self.assertIn('"tool": "<tool_name>"', formatted.messages[0].content)

    def test_keyword_router_is_used_when_llm_is_unavailable(self) -> None:
        with patch("services.rag.rag_service.get_model", return_value=None):
            tool_name, route_name = route_rag_tool("quy che hoc phi")

        self.assertEqual(tool_name, "academic_policy_rag")
        self.assertTrue(route_name.startswith("router_keyword_score:"))

    def test_strong_handbook_keyword_route_skips_llm_router(self) -> None:
        question = "Dieu kien dat danh hieu sinh vien Kha, Gioi, Xuat sac la gi?"

        with patch("services.rag.rag_service._route_rag_tool_by_llm") as llm_router:
            tool_name, route_name = route_rag_tool(question)

        self.assertEqual(tool_name, "student_handbook_rag")
        self.assertTrue(route_name.startswith("router_keyword_score:"))
        llm_router.assert_not_called()

    def test_keyword_router_prefers_handbook_for_nguoi_hoc_behavior_question(self) -> None:
        question = "Nguoi hoc khong duoc lam nhung hanh vi nao?"

        with patch("services.rag.rag_service._route_rag_tool_by_llm") as llm_router:
            tool_name, route_name = route_rag_tool(question)

        self.assertEqual(tool_name, "student_handbook_rag")
        self.assertTrue(route_name.startswith("router_keyword_score:"))
        llm_router.assert_not_called()

    def test_keyword_router_prefers_handbook_for_retake_improvement_question(self) -> None:
        question = "Học lại có được cải thiện điểm không?"

        with patch("services.rag.rag_service._route_rag_tool_by_llm") as llm_router:
            tool_name, route_name = route_rag_tool(question)

        self.assertEqual(tool_name, "student_handbook_rag")
        self.assertTrue(route_name.startswith("router_keyword_score:"))
        llm_router.assert_not_called()

    def test_keyword_router_prefers_handbook_for_study_preservation_question(self) -> None:
        question = "Sinh viên muốn bảo lưu cần làm gì?"

        with patch("services.rag.rag_service._route_rag_tool_by_llm") as llm_router:
            tool_name, route_name = route_rag_tool(question)

        self.assertEqual(tool_name, "student_handbook_rag")
        self.assertTrue(route_name.startswith("router_keyword_score:"))
        llm_router.assert_not_called()

    def test_keyword_router_prefers_handbook_for_year_specific_graduation_conditions(self) -> None:
        questions = (
            "Về năm 2022-2023, điều kiện tốt nghiệp là gì?",
            "Về năm 2025-2026, điều kiện tốt nghiệp là gì?",
            "Sinh viên cần đáp ứng điều kiện nào để được công nhận tốt nghiệp?",
        )

        for question in questions:
            with self.subTest(question=question):
                with patch("services.rag.rag_service._route_rag_tool_by_llm") as llm_router:
                    tool_name, route_name = route_rag_tool(question)

                self.assertEqual(tool_name, "student_handbook_rag")
                self.assertTrue(route_name.startswith("router_keyword_score:"))
                llm_router.assert_not_called()


class RetrievalFlowPlannerTests(unittest.TestCase):
    def test_retrieval_flow_prompt_with_json_example_formats_as_plain_text(self) -> None:
        prompt_text = _build_retrieval_flow_prompt(
            "ICTU co thong bao moi nhat gi hom nay?",
            "student_faq_rag",
        )

        formatted = _RAW_TEXT_PROMPT.invoke({"prompt": prompt_text})

        self.assertEqual(_RAW_TEXT_PROMPT.input_variables, ["prompt"])
        self.assertIn('"source": "local_data | web_search | hybrid"', formatted.messages[0].content)

    def test_llm_planner_can_choose_web_search_before_retrieval(self) -> None:
        question = "ICTU có nội dung nào cần tra cứu trực tuyến?"
        with (
            patch("services.rag.rag_service.get_model", return_value=SimpleNamespace(label="planner-model")),
            patch("services.rag.rag_service._llm_router_network_available", return_value=True),
            patch(
                "services.rag.rag_service.invoke_json_prompt_chain",
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
            plan = route_retrieval_flow(question, "student_faq_rag")

        self.assertEqual(plan.source, RETRIEVAL_WEB_SEARCH)
        self.assertEqual(plan.priority, RETRIEVAL_WEB_FIRST)
        self.assertTrue(plan.route.startswith("flow_llm:web_search:web_first"))
        prompt_template = chain_mock.call_args.args[0]
        prompt_input = chain_mock.call_args.args[1]
        self.assertEqual(prompt_template.input_variables, ["prompt"])
        self.assertIn("student_faq_rag", prompt_input["prompt"])
        self.assertIn("local_data", prompt_input["prompt"])
        self.assertIn("web_search", prompt_input["prompt"])
        self.assertIn("hybrid", prompt_input["prompt"])

    def test_realtime_query_forces_web_search_without_llm_planner(self) -> None:
        with patch("services.rag.rag_service._route_retrieval_flow_by_llm") as llm_planner:
            plan = route_retrieval_flow("ICTU hôm nay có gì mới?", "general_ictu_rag")

        self.assertEqual(plan.source, RETRIEVAL_WEB_SEARCH)
        self.assertEqual(plan.priority, RETRIEVAL_WEB_FIRST)
        self.assertTrue(plan.route.startswith("flow_realtime:web_search"))
        llm_planner.assert_not_called()

    def test_flow_falls_back_to_web_search_for_realtime_question_without_llm(self) -> None:
        with patch("services.rag.rag_service.get_model", return_value=None):
            plan = route_retrieval_flow("ICTU co thong bao moi nhat gi hom nay?", "student_faq_rag")

        self.assertEqual(plan.source, RETRIEVAL_WEB_SEARCH)
        self.assertEqual(plan.priority, RETRIEVAL_WEB_FIRST)

    def test_flow_falls_back_to_web_search_for_dated_thong_bao_question_without_llm(self) -> None:
        with patch("services.rag.rag_service.get_model", return_value=None):
            plan = route_retrieval_flow("ngày 13/5/2026 ICTU có thông báo j ko?", "student_faq_rag")

        self.assertEqual(plan.source, RETRIEVAL_WEB_SEARCH)
        self.assertEqual(plan.priority, RETRIEVAL_WEB_FIRST)

    def test_flow_falls_back_to_local_data_for_stable_handbook_question_without_llm(self) -> None:
        with patch("services.rag.rag_service.get_model", return_value=None):
            plan = route_retrieval_flow("Dieu kien dat danh hieu sinh vien Kha, Gioi, Xuat sac la gi?", "student_handbook_rag")

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
            patch("services.rag.rag_service.is_ictu_related_query", return_value=True),
            patch("services.rag.rag_service._build_planned_web_result", return_value=web_result),
            patch("services.rag.rag_service._load_tool_corpus") as load_corpus_mock,
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

    def test_web_search_plan_does_not_fall_back_to_unrelated_local_documents(self) -> None:
        plan = RetrievalFlowPlan(
            source=RETRIEVAL_WEB_SEARCH,
            priority=RETRIEVAL_WEB_FIRST,
            reason="Thong tin moi",
            confidence=0.9,
            route="flow_test:web",
        )

        with (
            patch("services.rag.rag_service.is_ictu_related_query", return_value=True),
            patch("services.rag.rag_service._build_planned_web_result", return_value=None),
            patch("services.rag.rag_service.embedding_backend_ready") as embedding_ready,
            patch("services.rag.rag_service._load_tool_corpus") as load_corpus_mock,
        ):
            result = retrieve_tool_context(
                "ICTU hôm nay có gì mới?",
                "test-web-empty",
                "general_ictu_rag",
                "router_test",
                retrieval_plan=plan,
            )

        self.assertEqual(result.mode, "web_search_empty")
        self.assertEqual(result.sources, [])
        self.assertEqual(result.chunks, [])
        embedding_ready.assert_not_called()
        load_corpus_mock.assert_not_called()


class RetrievalQueryBuilderTests(unittest.TestCase):
    def test_build_retrieval_query_keeps_short_follow_up_context(self) -> None:
        runtime = SimpleNamespace(
            session_memory={"session-1": [{"query": "So tay sinh vien K24 ap dung cho doi tuong nao?"}]},
            history_loader=lambda _sid: [],
        )

        query = build_retrieval_query(runtime, "session-1", "khóa k24")

        self.assertEqual(query, "So tay sinh vien K24 ap dung cho doi tuong nao? khóa k24")

    def test_build_retrieval_query_does_not_mix_previous_topic_into_standalone_realtime_question(self) -> None:
        runtime = SimpleNamespace(
            session_memory={"session-1": [{"query": "Điểm chuẩn ngành CNTT năm 2023 là bao nhiêu?"}]},
            history_loader=lambda _sid: [],
        )

        query = build_retrieval_query(runtime, "session-1", "ictu hôm nay có j mới")

        self.assertEqual(query, "ictu hôm nay có j mới")

    def test_build_retrieval_query_does_not_expand_short_question_with_explicit_new_topic(self) -> None:
        runtime = SimpleNamespace(
            session_memory={"session-1": [{"query": "Điểm chuẩn ngành CNTT năm 2023 là bao nhiêu?"}]},
            history_loader=lambda _sid: [],
        )

        query = build_retrieval_query(runtime, "session-1", "ictu tuyển sinh 2025")

        self.assertEqual(query, "ictu tuyển sinh 2025")

    def test_build_retrieval_query_does_not_mix_previous_topic_into_short_standalone_topic(self) -> None:
        runtime = SimpleNamespace(
            session_memory={"session-1": [{"query": "Điểm chuẩn ngành CNTT năm 2023 là bao nhiêu?"}]},
            history_loader=lambda _sid: [],
        )

        for message in ("học phí", "bhyt", "tốt nghiệp"):
            with self.subTest(message=message):
                query = build_retrieval_query(runtime, "session-1", message)

                self.assertEqual(query, message)

    def test_build_retrieval_query_keeps_explicit_follow_up_prefix(self) -> None:
        runtime = SimpleNamespace(
            session_memory={"session-1": [{"query": "Sổ tay sinh viên K24 áp dụng cho đối tượng nào?"}]},
            history_loader=lambda _sid: [],
        )

        query = build_retrieval_query(runtime, "session-1", "còn học phí")

        self.assertEqual(query, "Sổ tay sinh viên K24 áp dụng cho đối tượng nào? còn học phí")


class RetrievalScopeTests(unittest.TestCase):
    def test_strong_local_corpus_match_is_in_scope(self) -> None:
        runtime = SimpleNamespace(
            is_ictu_related_query=lambda _query: False,
            load_all_tool_documents=lambda: ("internal-doc",),
            search_documents=lambda _docs, _query, limit: [(106, "internal-doc")],
        )

        self.assertTrue(query_is_in_ictu_scope(runtime, "Khoa Công nghệ Thông tin được thành lập vào ngày nào?"))

    def test_weak_local_corpus_match_remains_out_of_scope(self) -> None:
        runtime = SimpleNamespace(
            is_ictu_related_query=lambda _query: False,
            load_all_tool_documents=lambda: ("internal-doc",),
            search_documents=lambda _docs, _query, limit: [(54, "internal-doc")],
        )

        self.assertFalse(query_is_in_ictu_scope(runtime, "Thời tiết Hà Nội hôm nay thế nào?"))


class RagLexicalQaTests(unittest.TestCase):
    def _doc(
        self,
        name: str,
        text: str,
        *,
        source: str | None = None,
        cohort_tags: frozenset[str] = frozenset(),
        year_values: frozenset[int] = frozenset(),
        max_year: int = 0,
    ) -> CorpusDocument:
        title = Path(name).stem
        source_name = source or f"So tay sinh vien cac nam/{name}"
        highest_year = max_year or max(year_values, default=0)
        return CorpusDocument(
            path=Path(name),
            source=source_name,
            title=title,
            text=text,
            text_lower=text.casefold(),
            normalized_text=_normalize_for_match(text),
            normalized_title=_normalize_for_match(title),
            normalized_source=_normalize_for_match(source_name),
            token_set=frozenset(_tokenize(f"{title}\\n{source_name}\\n{text}")),
            cohort_tags=cohort_tags,
            year_values=year_values,
            max_year=highest_year,
        )

    def test_exact_question_block_is_extracted_from_question_file(self) -> None:
        text = """
# Question Set

**Question:** Tai lieu so tay sinh vien dung de lam gi?
**Answer:** Tai lieu dung de cung cap thong tin chung cho sinh vien.

## Question 14

**Question:** Dieu kien dat danh hieu sinh vien Kha, Gioi, Xuat sac la gi?
**Answer:** Sinh vien Kha can ket qua hoc tap tu 2,50 den 3,19; sinh vien Gioi can tu 3,20 den 3,59; sinh vien Xuat sac can tu 3,60 tro len.
"""
        question = "Dieu kien dat danh hieu sinh vien Kha, Gioi, Xuat sac la gi?"
        snippet = _extract_relevant_snippet(self._doc("handbook.questions.md", text), question, _tokenize(question))

        self.assertIn("2,50 den 3,19", snippet)
        self.assertIn("3,60 tro len", snippet)
        self.assertNotIn("cung cap thong tin chung", snippet)

    def test_year_specific_bachelor_credit_query_extracts_concrete_total(self) -> None:
        question = "khóa 2024-2025 cần bao nhiêu tín chỉ để tốt nghiệp cử nhân?"
        documents = _load_tool_corpus("student_handbook_rag")

        matches = _search_documents(documents, question, limit=3)

        self.assertTrue(matches)
        self.assertEqual(
            matches[0][1].source,
            "student_handbooks/7. SO TAY SINH VIEN 2024-2025.md",
        )
        snippet = _extract_relevant_snippet(matches[0][1], question, _tokenize(question))
        self.assertIn("120 tín chỉ", snippet)
        self.assertIn("Chương trình đào tạo đại học (cử nhân)", snippet)

    def test_year_specific_graduation_conditions_use_matching_handbook(self) -> None:
        question = "Về năm 2022-2023, điều kiện tốt nghiệp là gì?"
        documents = _load_tool_corpus("student_handbook_rag")

        matches = _search_documents(documents, question, limit=3)

        self.assertTrue(matches)
        self.assertEqual(
            matches[0][1].source,
            "student_handbooks/5. SO TAY SINH VIEN 2022-2023.questions.md",
        )
        snippet = _extract_relevant_snippet(matches[0][1], question, _tokenize(question))
        self.assertIn("Điều kiện xét và công nhận tốt nghiệp", snippet)
        self.assertIn("điểm trung bình tích lũy toàn khóa từ 2,00 trở lên", snippet)

    def test_question_files_are_ranked_ahead_of_raw_context_for_exact_qa(self) -> None:
        question = "Dieu kien dat danh hieu sinh vien Kha, Gioi, Xuat sac la gi?"
        raw_doc = self._doc(
            "handbook.md",
            """
### Q14. Dieu kien dat danh hieu sinh vien Kha, Gioi, Xuat sac la gi?

Sinh vien Kha can ket qua hoc tap tu 2,50 den 3,19.
""",
        )
        question_doc = self._doc(
            "handbook.questions.md",
            """
**Question:** Dieu kien dat danh hieu sinh vien Kha, Gioi, Xuat sac la gi?
**Answer:** Sinh vien Kha can ket qua hoc tap tu 2,50 den 3,19; sinh vien Gioi can tu 3,20 den 3,59; sinh vien Xuat sac can tu 3,60 tro len.
""",
        )

        matches = _search_documents((raw_doc, question_doc), question, limit=2)

        self.assertEqual(matches[0][1].path.name, "handbook.questions.md")

    def test_retake_improvement_exact_question_extracts_answer(self) -> None:
        text = """
**Question:** Người học không được làm những hành vi nào?
**Answer:** Người học không được thực hiện các hành vi pháp luật cấm.

## Question 69

**Question:** Học lại có được cải thiện điểm không?
**Answer:** Có. Đối với học phần đã có kết quả đạt điểm C hoặc D, sinh viên được phép đăng ký học lại để cải thiện điểm; điểm cao nhất của các lần học là điểm chính thức của học phần.
"""
        question = "Học lại có được cải thiện điểm không?"
        snippet = _extract_relevant_snippet(self._doc("handbook.questions.md", text), question, _tokenize(question))

        self.assertIn("được phép đăng ký học lại để cải thiện điểm", snippet)
        self.assertIn("điểm cao nhất", snippet)
        self.assertNotIn("pháp luật cấm", snippet)

    def test_year_specific_query_prefers_matching_handbook_file(self) -> None:
        question = "So tay sinh vien 2024-2025 la tai lieu nao?"
        handbook_2425 = self._doc(
            "SO TAY SINH VIEN 2024-2025.md",
            "Tai lieu so tay sinh vien cho nam hoc 2024-2025.",
            year_values=frozenset({2024, 2025}),
            max_year=2025,
        )
        handbook_2526 = self._doc(
            "SO TAY SINH VIEN 2025-2026.md",
            "Tai lieu so tay sinh vien cho nam hoc 2025-2026.",
            year_values=frozenset({2025, 2026}),
            max_year=2026,
        )

        matches = _search_documents((handbook_2526, handbook_2425), question, limit=2)

        self.assertTrue(matches)
        self.assertEqual(matches[0][1].path.name, "SO TAY SINH VIEN 2024-2025.md")

    def test_year_range_query_prefers_exact_year_pair(self) -> None:
        question = "So tay sinh vien 2025-2026 ap dung cho doi tuong nao?"
        handbook_2425 = self._doc(
            "SO TAY SINH VIEN 2024-2025.questions.md",
            "So tay sinh vien 2024-2025 ap dung cho sinh vien khoa 23.",
            year_values=frozenset({2024, 2025}),
            max_year=2025,
        )
        handbook_2526 = self._doc(
            "SO TAY SINH VIEN 2025-2026.questions.md",
            "So tay sinh vien 2025-2026 ap dung cho sinh vien khoa 24.",
            year_values=frozenset({2025, 2026}),
            max_year=2026,
        )

        matches = _search_documents((handbook_2425, handbook_2526), question, limit=2)

        self.assertTrue(matches)
        self.assertEqual(matches[0][1].path.name, "SO TAY SINH VIEN 2025-2026.questions.md")

    def test_cohort_query_prefers_matching_handbook_cohort(self) -> None:
        question = "So tay sinh vien khoa 24 ap dung cho nam hoc nao?"
        handbook_k23 = self._doc(
            "SO TAY SINH VIEN 2024-2025.md",
            "Thong tin huong dan cho sinh vien khoa 23.",
            cohort_tags=frozenset({"k23"}),
            year_values=frozenset({2024, 2025}),
            max_year=2025,
        )
        handbook_k24 = self._doc(
            "SO TAY SINH VIEN 2025-2026.md",
            "Thong tin huong dan cho sinh vien khoa 24.",
            cohort_tags=frozenset({"k24"}),
            year_values=frozenset({2025, 2026}),
            max_year=2026,
        )

        matches = _search_documents((handbook_k23, handbook_k24), question, limit=2)

        self.assertTrue(matches)
        self.assertEqual(matches[0][1].path.name, "SO TAY SINH VIEN 2025-2026.md")
if __name__ == "__main__":
    unittest.main()
