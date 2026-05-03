from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import services.vector_store_service as vector_store_service
from services.document_service import reingest_uploaded_documents
from services.vector_store_service import smart_chunk


class SmartChunkTests(unittest.TestCase):
    def test_smart_chunk_uses_runtime_chunk_size_and_overlap(self) -> None:
        text = " ".join(f"w{i}" for i in range(1, 13))

        with (
            patch.object(vector_store_service.settings, "CHUNK_SIZE", 5),
            patch.object(vector_store_service.settings, "CHUNK_OVERLAP", 2),
            patch("services.vector_store_service.count_tokens", side_effect=lambda value: len(value.split())),
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
            patch("services.vector_store_service.count_tokens", side_effect=lambda value: len(value.split())),
        ):
            chunks = smart_chunk(text, "handbook.md")

        section_two = [chunk for chunk in chunks if chunk["title"] == "Hoc bong"]
        self.assertTrue(section_two)
        self.assertTrue(all(chunk["level"] == 2 for chunk in section_two))
        self.assertTrue(all("alpha5" not in chunk["text"] and "alpha6" not in chunk["text"] for chunk in section_two))


class _FakeCollection:
    def __init__(self) -> None:
        self._count = 1

    def count(self) -> int:
        return self._count


class ReingestPipelineTests(unittest.TestCase):
    def test_reingest_reloads_seed_and_uploaded_sources(self) -> None:
        with tempfile.TemporaryDirectory(dir="E:\\new-test") as temp_dir:
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
                    "services.document_service._iter_seed_source_records",
                    return_value=[(seed_path, "student_handbook_rag", "seed.md")],
                ),
                patch(
                    "services.document_service._iter_uploaded_source_records",
                    return_value=[(upload_path, "student_faq_rag", "uploads/student_faq_rag/upload.md")],
                ),
                patch("services.document_service.reset_vectorstore"),
                patch("services.document_service.get_collection", return_value=collection),
                patch("services.document_service.add_documents", side_effect=fake_add_documents) as add_documents_mock,
                patch("services.document_service.clear_rag_corpus_cache") as clear_cache_mock,
            ):
                total_files, total_chunks = reingest_uploaded_documents()

        self.assertEqual(total_files, 2)
        self.assertEqual(total_chunks, 5)
        self.assertEqual(
            [call.kwargs["source_name"] for call in add_documents_mock.call_args_list],
            ["seed.md", "uploads/student_faq_rag/upload.md"],
        )
        clear_cache_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
