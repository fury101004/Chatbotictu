from __future__ import annotations

import unittest
from unittest.mock import patch

import services.vector.vector_store_service as vector_store_service
from services.vector.vector_store_service import add_documents, smart_chunk


class _CapturingCollection:
    def __init__(self) -> None:
        self.add_calls: list[dict] = []
        self.deleted_where: list[dict] = []

    def delete(self, where=None) -> None:
        self.deleted_where.append(where or {})

    def add(self, *, documents, metadatas, ids) -> None:
        self.add_calls.append(
            {
                "documents": documents,
                "metadatas": metadatas,
                "ids": ids,
            }
        )


class ChunkMetadataExtractionTests(unittest.TestCase):
    def test_smart_chunk_extracts_chapter_section_and_page(self) -> None:
        text = """
# Sổ tay sinh viên 2025-2026
Trang 12
## Học bổng
Điều kiện xét học bổng theo năm học.
""".strip()

        with (
            patch.object(vector_store_service.settings, "CHUNK_SIZE", 200),
            patch.object(vector_store_service.settings, "CHUNK_OVERLAP", 0),
            patch("services.vector.vector_store_service.count_tokens", side_effect=lambda value: len(value.split())),
        ):
            chunks = smart_chunk(text, "so-tay.md", source_name="Sổ tay sinh viên 2025-2026.md")

        self.assertTrue(chunks)
        self.assertEqual(chunks[-1]["chapter"], "Sổ tay sinh viên 2025-2026")
        self.assertIn("Học bổng", chunks[-1]["section"])
        self.assertEqual(chunks[-1]["page_number"], 12)

    def test_add_documents_persists_enriched_metadata(self) -> None:
        collection = _CapturingCollection()
        text = """
# Sổ tay sinh viên 2025-2026
Trang 8
## Điều kiện học bổng
Thông tin cho sinh viên.
""".strip()

        with (
            patch("services.vector.vector_store_service.get_collection", return_value=collection),
            patch("services.vector.vector_store_service._rebuild_bm25"),
            patch("services.vector.vector_store_service.inject_bot_rule"),
            patch("services.vector.vector_store_service.count_tokens", side_effect=lambda value: len(value.split())),
            patch.object(vector_store_service.settings, "CHUNK_SIZE", 120),
            patch.object(vector_store_service.settings, "CHUNK_OVERLAP", 0),
        ):
            add_documents(
                file_content=text,
                filename="SO TAY SINH VIEN 2025-2026.md",
                source_name="uploads/student_handbook_rag/SO TAY SINH VIEN 2025-2026.md",
                tool_name="student_handbook_rag",
            )

        self.assertTrue(collection.add_calls)
        metadatas = [meta for call in collection.add_calls for meta in call["metadatas"]]
        first_meta = metadatas[0]
        self.assertEqual(first_meta["tool_name"], "student_handbook_rag")
        self.assertEqual(first_meta["academic_year"], "2025-2026")
        self.assertEqual(first_meta["document_type"], "student_handbook")
        self.assertTrue(any(meta["page_number"] == 8 for meta in metadatas))
        self.assertTrue(any("Điều kiện học bổng" in meta["section"] for meta in metadatas))


if __name__ == "__main__":
    unittest.main()

