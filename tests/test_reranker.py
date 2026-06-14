from __future__ import annotations

import unittest
from unittest.mock import patch

from langchain_core.documents import Document

from services.reranker import CrossEncoderReranker, rerank_langchain_documents


class RerankerTests(unittest.TestCase):
    def test_rerank_orders_documents_by_cross_encoder_score(self) -> None:
        class FakeModel:
            def predict(self, pairs):
                self.pairs = pairs
                return [0.2, 0.95, 0.5]

        with patch("services.reranker.CrossEncoder", return_value=FakeModel()):
            reranker = CrossEncoderReranker("fake-model", top_k=2)

            result = reranker.rerank("hoc phi", ["doc-a", "doc-b", "doc-c"])

        self.assertEqual(result, ["doc-b", "doc-c"])

    def test_rerank_falls_back_to_original_order_when_model_load_fails(self) -> None:
        with patch("services.reranker.CrossEncoder", side_effect=RuntimeError("download blocked")):
            reranker = CrossEncoderReranker("fake-model", top_k=2)

            result = reranker.rerank("hoc phi", ["doc-a", "doc-b", "doc-c"])

        self.assertEqual(result, ["doc-a", "doc-b"])

    def test_rerank_falls_back_to_original_order_when_prediction_fails(self) -> None:
        class BrokenModel:
            def predict(self, pairs):
                raise RuntimeError("predict failed")

        with patch("services.reranker.CrossEncoder", return_value=BrokenModel()):
            reranker = CrossEncoderReranker("fake-model", top_k=2)

            result = reranker.rerank("hoc phi", ["doc-a", "doc-b", "doc-c"])

        self.assertEqual(result, ["doc-a", "doc-b"])

    def test_langchain_rerank_persists_pre_and_post_rerank_rank(self) -> None:
        class FakeReranker:
            top_k = 2

            def rank(self, query, documents):
                return [1, 0]

        documents = [
            Document(page_content="doc-a", metadata={"fusion_method": "rrf", "pre_rerank_rank": 1}),
            Document(page_content="doc-b", metadata={"fusion_method": "rrf", "pre_rerank_rank": 2}),
        ]

        result = rerank_langchain_documents("hoc phi", documents, reranker=FakeReranker())

        self.assertEqual([document.page_content for document in result], ["doc-b", "doc-a"])
        self.assertEqual(result[0].metadata["pre_rerank_rank"], 2)
        self.assertEqual(result[0].metadata["post_rerank_rank"], 1)
        self.assertEqual(result[0].metadata["fusion_method"], "rrf")


if __name__ == "__main__":
    unittest.main()
