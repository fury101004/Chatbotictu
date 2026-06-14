from __future__ import annotations

import unittest
from collections import defaultdict, deque

from pipelines.vector_query_pipeline import (
    FUSION_RRF,
    FUSION_WEIGHTED,
    normalize_fusion_method,
    reciprocal_rank_fusion,
    run_hybrid_query,
    weighted_score_fusion,
)


class ReciprocalRankFusionTests(unittest.TestCase):
    def test_rrf_combines_independent_rankings_by_stable_id(self) -> None:
        scores, ranked_ids = reciprocal_rank_fusion(
            [
                ["chunk-a", "chunk-b", "chunk-c"],
                ["chunk-b", "chunk-c", "chunk-d"],
            ],
            k=60,
        )

        self.assertEqual(ranked_ids, ["chunk-b", "chunk-c", "chunk-a", "chunk-d"])
        self.assertAlmostEqual(scores["chunk-b"], 1 / 62 + 1 / 61)
        self.assertAlmostEqual(scores["chunk-c"], 1 / 63 + 1 / 62)
        self.assertAlmostEqual(scores["chunk-a"], 1 / 61)
        self.assertAlmostEqual(scores["chunk-d"], 1 / 63)

    def test_rrf_k_is_configurable(self) -> None:
        scores_k_10, _ = reciprocal_rank_fusion([["chunk-a"]], k=10)
        scores_k_60, _ = reciprocal_rank_fusion([["chunk-a"]], k=60)

        self.assertEqual(scores_k_10["chunk-a"], 1 / 11)
        self.assertEqual(scores_k_60["chunk-a"], 1 / 61)
        self.assertGreater(scores_k_10["chunk-a"], scores_k_60["chunk-a"])

    def test_rrf_rejects_invalid_k(self) -> None:
        with self.assertRaises(ValueError):
            reciprocal_rank_fusion([["chunk-a"]], k=0)


class FusionMethodTests(unittest.TestCase):
    def test_rrf_is_default_for_unknown_or_empty_method(self) -> None:
        self.assertEqual(normalize_fusion_method(""), FUSION_RRF)
        self.assertEqual(normalize_fusion_method("unknown"), FUSION_RRF)

    def test_weighted_fusion_remains_available(self) -> None:
        scores, ranked_ids = weighted_score_fusion(
            ["chunk-a", "chunk-b"],
            vector_scores={"chunk-a": 1.0, "chunk-b": 0.0},
            bm25_scores={"chunk-a": 0.0, "chunk-b": 1.0},
            alpha=0.8,
        )

        self.assertEqual(normalize_fusion_method("weighted"), FUSION_WEIGHTED)
        self.assertEqual(ranked_ids, ["chunk-a", "chunk-b"])
        self.assertAlmostEqual(scores["chunk-a"], 0.8)
        self.assertAlmostEqual(scores["chunk-b"], 0.2)


class HybridQueryRrfIntegrationTests(unittest.TestCase):
    def test_hybrid_query_applies_tool_filter_and_persists_rrf_rank_metadata(self) -> None:
        class FakeBm25:
            def get_scores(self, query_tokens):
                return [1.0, 3.0, 2.0, 100.0]

        class FakeCollection:
            records = {
                "chunk-a": ("doc-a", {"source": "a.md", "tool_name": "student_handbook_rag"}),
                "chunk-b": ("doc-b", {"source": "b.md", "tool_name": "student_handbook_rag"}),
                "chunk-c": ("doc-c", {"source": "c.md", "tool_name": "student_handbook_rag"}),
                "chunk-d": ("doc-d", {"source": "d.md", "tool_name": "student_faq_rag"}),
                "BOT_RULE_001": ("rule", {"source": "BOT_RULE"}),
            }

            def __init__(self):
                self.query_where = None

            def count(self):
                return len(self.records)

            def query(self, **kwargs):
                self.query_where = kwargs.get("where")
                return {
                    "ids": [["chunk-a", "chunk-b", "chunk-c"]],
                    "distances": [[0.1, 0.2, 0.3]],
                    "documents": [["doc-a", "doc-b", "doc-c"]],
                    "metadatas": [[self.records[key][1] for key in ("chunk-a", "chunk-b", "chunk-c")]],
                }

            def get(self, ids=None, where=None, include=None):
                if where:
                    selected_ids = [
                        key
                        for key, (_document, metadata) in self.records.items()
                        if metadata.get("tool_name") == where.get("tool_name")
                    ]
                else:
                    selected_ids = list(ids or [])
                return {
                    "ids": selected_ids,
                    "documents": [self.records[key][0] for key in selected_ids],
                    "metadatas": [self.records[key][1] for key in selected_ids],
                }

        collection = FakeCollection()
        documents, metadatas, extra = run_hybrid_query(
            collection=collection,
            query="hoc phi",
            user_id="unit",
            n_results=4,
            alpha=0.75,
            fusion_method="rrf",
            rrf_k=60,
            metadata_filter={"tool_name": "student_handbook_rag"},
            bm25_index=FakeBm25(),
            all_ids=["chunk-a", "chunk-b", "chunk-c", "chunk-d"],
            tokenize_text_fn=lambda text: text.split(),
            bot_rule_id="BOT_RULE_001",
            session_memory=defaultdict(lambda: deque(maxlen=5)),
            stats={"total_queries": 0, "avg_time": 0.0, "popular_files": defaultdict(int)},
        )

        self.assertEqual(collection.query_where, {"tool_name": "student_handbook_rag"})
        self.assertEqual(documents[:2], ["rule", "doc-b"])
        self.assertNotIn("doc-d", documents)
        self.assertEqual(metadatas[1]["fusion_method"], "rrf")
        self.assertEqual(metadatas[1]["pre_rerank_rank"], 1)
        self.assertEqual(extra["fusion_method"], "rrf")


if __name__ == "__main__":
    unittest.main()
