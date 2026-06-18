from __future__ import annotations

import unittest
from unittest.mock import patch

from repositories.vector_repository import (
    count_vector_chunks,
    delete_vector_chunk,
    delete_vector_source,
    fetch_documents_by_source,
    list_vector_chunks,
    list_vector_sources,
)


class _FakeCollection:
    def __init__(self) -> None:
        self.delete_calls: list[dict] = []

    def delete(self, **kwargs) -> None:
        self.delete_calls.append(kwargs)


class _FakeReadonlyCollection:
    def __init__(self) -> None:
        self.get_calls: list[dict] = []
        self.count_calls = 0

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        include = kwargs.get("include", [])
        payload = {"ids": [], "metadatas": []}
        if "documents" in include:
            payload["documents"] = []
        return payload

    def count(self) -> int:
        self.count_calls += 1
        return 7


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


class VectorReadonlyAccessTests(unittest.TestCase):
    def test_read_helpers_use_readonly_collection(self) -> None:
        collection = _FakeReadonlyCollection()

        with (
            patch("repositories.vector_repository.get_vector_collection_readonly", return_value=collection),
            patch("repositories.vector_repository.get_vector_collection") as writable_mock,
        ):
            self.assertEqual(count_vector_chunks(), 7)
            self.assertEqual(list_vector_chunks(include_documents=False), {"ids": [], "metadatas": []})
            self.assertEqual(list_vector_sources(), set())
            self.assertEqual(fetch_documents_by_source("uploads/student_faq_rag/guide.md"), ([], []))

        writable_mock.assert_not_called()
        self.assertGreaterEqual(collection.count_calls, 1)
        self.assertGreaterEqual(len(collection.get_calls), 3)


if __name__ == "__main__":
    unittest.main()
