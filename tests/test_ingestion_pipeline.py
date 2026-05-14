from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipelines.document_admin_pipeline import build_vector_manager_summary
from pipelines.indexing_pipeline import index_document
import services.vector.vector_store_service as vector_store_service
from services.content.document_service import reingest_uploaded_documents
from services.vector.vector_store_service import smart_chunk


class SmartChunkTests(unittest.TestCase):
    def test_smart_chunk_uses_runtime_chunk_size_and_overlap(self) -> None:
        text = " ".join(f"w{i}" for i in range(1, 13))

        with (
            patch.object(vector_store_service.settings, "CHUNK_SIZE", 5),
            patch.object(vector_store_service.settings, "CHUNK_OVERLAP", 2),
            patch("services.vector.vector_store_service.count_tokens", side_effect=lambda value: len(value.split())),
        ):
            chunks = smart_chunk(text, "guide.md")

        self.assertEqual(
            [chunk["text"] for chunk in chunks],
            [
                "w1 w2 w3 w4 w5",
                "w4 w5 w6 w7 w8",
                "w7 w8 w9 w10 w11",
                "w10 w11 w12",
            ],
        )
        self.assertTrue(all(chunk["level"] == 1 for chunk in chunks))
        self.assertTrue(all(chunk["word_count"] == len(chunk["text"].split()) for chunk in chunks))

    def test_smart_chunk_resets_overlap_when_new_heading_starts(self) -> None:
        text = """
# So tay 2024-2025
alpha1 alpha2 alpha3 alpha4 alpha5 alpha6

## Hoc bong
beta1 beta2 beta3 beta4 beta5 beta6
""".strip()

        with (
            patch.object(vector_store_service.settings, "CHUNK_SIZE", 5),
            patch.object(vector_store_service.settings, "CHUNK_OVERLAP", 2),
            patch("services.vector.vector_store_service.count_tokens", side_effect=lambda value: len(value.split())),
        ):
            chunks = smart_chunk(text, "handbook.md")

        section_two = [chunk for chunk in chunks if chunk["title"] == "Hoc bong"]
        self.assertTrue(section_two)
        self.assertTrue(all(chunk["level"] == 2 for chunk in section_two))
        self.assertTrue(all("alpha5" not in chunk["text"] and "alpha6" not in chunk["text"] for chunk in section_two))

    def test_smart_chunk_prefers_sentence_boundary_near_limit(self) -> None:
        text = "Cau mot co bon tu. Cau hai keo dai them nhieu tu de qua gioi han."

        with (
            patch.object(vector_store_service.settings, "CHUNK_SIZE", 7),
            patch.object(vector_store_service.settings, "CHUNK_OVERLAP", 0),
            patch("services.vector.vector_store_service.count_tokens", side_effect=lambda value: len(value.split())),
        ):
            chunks = smart_chunk(text, "guide.md")

        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["text"], "Cau mot co bon tu.")


class _FakeCollection:
    def __init__(self) -> None:
        self._count = 1

    def count(self) -> int:
        return self._count


class ReingestPipelineTests(unittest.TestCase):
    def test_reingest_reloads_seed_and_uploaded_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            seed_path = temp_root / "seed.md"
            upload_path = temp_root / "upload.md"
            seed_path.write_text("# Seed\n\nNoi dung seed", encoding="utf-8")
            upload_path.write_text("# Upload\n\nNoi dung upload", encoding="utf-8")

            collection = _FakeCollection()

            def fake_add_documents(*, filename: str, **kwargs) -> None:
                if filename == "seed.md":
                    collection._count += 3
                elif filename == "upload.md":
                    collection._count += 2

            with (
                patch(
                    "services.content.document_service._iter_seed_source_records",
                    return_value=[(seed_path, "student_handbook_rag", "seed.md")],
                ),
                patch(
                    "services.content.document_service._iter_uploaded_source_records",
                    return_value=[(upload_path, "student_faq_rag", "uploads/student_faq_rag/upload.md")],
                ),
                patch("services.content.document_service.reset_vectorstore"),
                patch("services.content.document_service.get_collection", return_value=collection),
                patch("services.content.document_service.add_documents", side_effect=fake_add_documents) as add_documents_mock,
                patch("services.content.document_service.clear_rag_corpus_cache") as clear_cache_mock,
            ):
                total_files, total_chunks = reingest_uploaded_documents()

        self.assertEqual(total_files, 2)
        self.assertEqual(total_chunks, 5)
        self.assertEqual(
            [call.kwargs["source_name"] for call in add_documents_mock.call_args_list],
            ["seed.md", "uploads/student_faq_rag/upload.md"],
        )
        clear_cache_mock.assert_called_once()


class IndexingPipelineSafetyTests(unittest.TestCase):
    def test_index_document_does_not_delete_existing_when_chunking_fails(self) -> None:
        class _Collection:
            def __init__(self) -> None:
                self.deleted = False

            def delete(self, *, where):  # type: ignore[no-untyped-def]
                self.deleted = True

            def add(self, **kwargs):  # type: ignore[no-untyped-def]
                raise AssertionError("add should not be called when no chunk is generated")

        collection = _Collection()

        index_document(
            file_content="test",
            filename="sample.md",
            version="v1",
            source_name="sample.md",
            tool_name="student_handbook_rag",
            collection_getter=lambda: collection,
            smart_chunk_fn=lambda *_args, **_kwargs: [],
            extract_academic_year_fn=lambda *_args, **_kwargs: "2024-2025",
            infer_document_type_fn=lambda *_args, **_kwargs: "handbook",
            rebuild_bm25_fn=lambda: None,
            inject_bot_rule_fn=lambda *_args, **_kwargs: None,
        )

        self.assertFalse(collection.deleted)


class VectorManagerSummaryTests(unittest.TestCase):
    def test_build_vector_manager_summary_raises_on_mismatched_payload_lengths(self) -> None:
        payload = {
            "ids": ["id-1"],
            "documents": [],
            "metadatas": [{"source": "test.md"}],
        }

        with self.assertRaises(ValueError):
            build_vector_manager_summary(
                payload,
                rag_tool_order=["student_handbook_rag"],
                rag_tool_profiles={"student_handbook_rag": {"label": "Handbook", "description": ""}},
                infer_vector_tool_name=lambda *_args, **_kwargs: "student_handbook_rag",
                is_valid_rag_tool=lambda tool: tool == "student_handbook_rag",
                display_vector_source=lambda source: source,
                upload_source_prefix="uploads",
                limit_per_file=5,
            )

if __name__ == "__main__":
    unittest.main()

