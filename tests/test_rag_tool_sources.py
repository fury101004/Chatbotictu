from __future__ import annotations

import unittest

from config.rag_tools import (
    QA_ROOT,
    RAG_TOOL_CORPUS_DIRS,
    RAG_TOOL_ORDER,
    detect_tool_from_path,
    get_tool_profile,
)
from services.rag.rag_service import (
    _load_tool_corpus,
    retrieve_academic_policy_context,
    retrieve_general_ictu_context,
    retrieve_student_faq_context,
    retrieve_student_handbook_context,
)
from services.rag.rag_corpus import _search_documents


class RagToolSourceOwnershipTests(unittest.TestCase):
    def test_standardized_tool_order_contains_four_controlled_tools(self) -> None:
        self.assertEqual(
            RAG_TOOL_ORDER,
            [
                "student_handbook_rag",
                "academic_policy_rag",
                "student_faq_rag",
                "general_ictu_rag",
            ],
        )

    def test_each_tool_exposes_a_distinct_retrieval_function(self) -> None:
        retrieval_functions = {
            retrieve_student_handbook_context,
            retrieve_academic_policy_context,
            retrieve_student_faq_context,
            retrieve_general_ictu_context,
        }
        self.assertEqual(len(retrieval_functions), 4)

    def test_each_tool_uses_one_existing_dedicated_seed_directory(self) -> None:
        resolved_qa_root = QA_ROOT.resolve()
        resolved_roots = []

        for tool_name in RAG_TOOL_ORDER:
            with self.subTest(tool_name=tool_name):
                expected_root = RAG_TOOL_CORPUS_DIRS[tool_name].resolve()
                configured_roots = [
                    path.resolve()
                    for path in get_tool_profile(tool_name)["corpus_paths"]
                ]

                self.assertEqual(configured_roots, [expected_root])
                self.assertEqual(
                    get_tool_profile(tool_name)["metadata_filter"],
                    {"tool_name": tool_name},
                )
                self.assertNotEqual(expected_root, resolved_qa_root)
                self.assertTrue(expected_root.is_dir())
                resolved_roots.append(expected_root)

        self.assertEqual(len(resolved_roots), len(set(resolved_roots)))

    def test_paths_inside_each_seed_directory_map_to_its_owner(self) -> None:
        for tool_name, root in RAG_TOOL_CORPUS_DIRS.items():
            with self.subTest(tool_name=tool_name):
                self.assertEqual(
                    detect_tool_from_path(root / "example.md"),
                    tool_name,
                )

    def test_file_at_shared_corpus_root_has_no_owner(self) -> None:
        self.assertIsNone(detect_tool_from_path(QA_ROOT / "shared.md"))

    def test_student_handbook_corpus_contains_academic_warning_exit_faq(self) -> None:
        documents = _search_documents(
            _load_tool_corpus("student_handbook_rag"),
            "Làm thế nào để sinh viên thoát khỏi diện cảnh báo học tập?",
            limit=3,
        )

        self.assertTrue(documents)
        self.assertEqual(documents[0][1].path.name, "8. SO TAY SINH VIEN 2025-2026.questions.md")


if __name__ == "__main__":
    unittest.main()
