from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from services.rag.langchain_retrievers import (
    CorpusLexicalRetriever,
    VectorStoreRetriever,
    WebKnowledgeRetriever,
    WebSearchRetriever,
)


class LangChainRetrieverTests(unittest.TestCase):
    def test_corpus_lexical_retriever_returns_langchain_documents(self) -> None:
        fake_doc = SimpleNamespace(
            path=Path("handbook.md"),
            source="uploads/student_handbook_rag/handbook.md",
            title="So tay",
            text="Noi dung so tay",
        )

        retriever = CorpusLexicalRetriever(
            document_supplier=lambda: (fake_doc,),
            search_fn=lambda documents, query, limit=4: [(11, fake_doc)],
            snippet_fn=lambda doc, query, tokens: "Doan trich phu hop",
            tool_name="student_handbook_rag",
            limit=4,
        )

        documents = retriever.invoke("so tay sinh vien")

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].page_content, "Doan trich phu hop")
        self.assertEqual(documents[0].metadata["tool_name"], "student_handbook_rag")
        self.assertIn("score", documents[0].metadata)
        self.assertIn("context_entry", documents[0].metadata)

    def test_vector_store_retriever_queries_hybrid_search(self) -> None:
        retriever = VectorStoreRetriever(
            query_fn=lambda query, user_id, n_results, alpha: (
                ["Chunk A"],
                [{"source": "policy.md", "title": "Hoc phi"}],
                {},
            ),
            collection_getter=lambda: None,
            user_id="session-1",
            n_results=20,
            alpha=0.5,
        )

        documents = retriever.invoke("hoc phi")

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].page_content, "Chunk A")
        self.assertEqual(documents[0].metadata["source"], "policy.md")

    def test_vector_store_retriever_filters_exact_academic_year(self) -> None:
        retriever = VectorStoreRetriever(
            query_fn=lambda query, user_id, n_results, alpha: (
                ["Rule", "Chunk 2024", "Chunk 2025", "Other"],
                [
                    {"source": "BOT_RULE"},
                    {"source": "student_handbooks/SO TAY SINH VIEN 2024-2025.md", "academic_year": "2024-2025"},
                    {"source": "student_handbooks/SO TAY SINH VIEN 2025-2026.md", "academic_year": "2025-2026"},
                    {"source": "student_handbooks/guide.md", "academic_year": ""},
                ],
                {},
            ),
            collection_getter=lambda: None,
            user_id="session-1",
            n_results=20,
            alpha=0.5,
        )

        documents = retriever.invoke("Sổ tay sinh viên 2025-2026 áp dụng cho đối tượng nào?")

        self.assertEqual([doc.metadata["source"] for doc in documents], [
            "BOT_RULE",
            "student_handbooks/SO TAY SINH VIEN 2025-2026.md",
        ])

    def test_web_retrievers_wrap_web_matches_as_documents(self) -> None:
        knowledge_retriever = WebKnowledgeRetriever(
            search_fn=lambda query, limit=4: [
                SimpleNamespace(
                    question="Hoc phi moi nhat?",
                    answer="Thong tin hoc phi.",
                    score=8,
                    entry_id="wk1",
                    expires_at="2026-12-31",
                    sources=["https://ictu.edu.vn/hoc-phi"],
                    source_text="Thong bao hoc phi",
                )
            ],
            tool_name="student_faq_rag",
        )
        search_retriever = WebSearchRetriever(
            search_fn=lambda query, limit=4: [
                SimpleNamespace(
                    title="Thong bao hoc phi",
                    url="https://ictu.edu.vn/hoc-phi",
                    snippet="Hoc phi 2026",
                    text="Noi dung thong bao hoc phi",
                )
            ],
            tool_name="student_faq_rag",
        )

        knowledge_docs = knowledge_retriever.invoke("hoc phi moi nhat")
        search_docs = search_retriever.invoke("hoc phi moi nhat")

        self.assertEqual(knowledge_docs[0].metadata["source_type"], "web_knowledge")
        self.assertEqual(search_docs[0].metadata["source_type"], "web_search")
        self.assertIn("context_entry", knowledge_docs[0].metadata)
        self.assertIn("context_entry", search_docs[0].metadata)


if __name__ == "__main__":
    unittest.main()

