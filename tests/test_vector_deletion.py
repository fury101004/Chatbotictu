from __future__ import annotations

import unittest
from unittest.mock import patch

from repositories.vector_repository import delete_vector_chunk, delete_vector_source


class _FakeCollection:
    def __init__(self) -> None:
        self.delete_calls: list[dict] = []

    def delete(self, **kwargs) -> None:
        self.delete_calls.append(kwargs)


class VectorDeletionTests(unittest.TestCase):
    def test_delete_source_targets_every_chunk_with_the_same_source(self) -> None:
        collection = _FakeCollection()

        with patch("repositories.vector_repository.get_vector_collection", return_value=collection):
            delete_vector_source("uploads/student_faq_rag/guide.md")

        self.assertEqual(
            collection.delete_calls,
            [{"where": {"source": "uploads/student_faq_rag/guide.md"}}],
        )

    def test_delete_chunk_targets_only_the_selected_chunk_id(self) -> None:
        collection = _FakeCollection()

        with patch("repositories.vector_repository.get_vector_collection", return_value=collection):
            delete_vector_chunk("guide__00003")

        self.assertEqual(collection.delete_calls, [{"ids": ["guide__00003"]}])


if __name__ == "__main__":
    unittest.main()
