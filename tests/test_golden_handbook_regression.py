from __future__ import annotations

import unittest
from pathlib import Path

from services.rag_corpus import _normalize_for_match, _search_documents, _tokenize
from services.rag_types import CorpusDocument


class GoldenHandbookYearRegressionTests(unittest.TestCase):
    def _doc(self, file_name: str, text: str, years: set[int], cohort: str) -> CorpusDocument:
        source = f"So tay sinh vien cac nam/{file_name}"
        title = Path(file_name).stem
        return CorpusDocument(
            path=Path(file_name),
            source=source,
            title=title,
            text=text,
            text_lower=text.casefold(),
            normalized_text=_normalize_for_match(text),
            normalized_title=_normalize_for_match(title),
            normalized_source=_normalize_for_match(source),
            token_set=frozenset(_tokenize(f"{title}\n{source}\n{text}")),
            cohort_tags=frozenset({cohort}),
            year_values=frozenset(years),
            max_year=max(years),
        )

    def setUp(self) -> None:
        self.docs = (
            self._doc(
                "SO TAY SINH VIEN 2023-2024.questions.md",
                "Question: So tay sinh vien 2023-2024 ap dung cho doi tuong nao? Answer: Sinh vien khoa 22.",
                {2023, 2024},
                "k22",
            ),
            self._doc(
                "SO TAY SINH VIEN 2024-2025.questions.md",
                "Question: So tay sinh vien 2024-2025 ap dung cho doi tuong nao? Answer: Sinh vien khoa 23.",
                {2024, 2025},
                "k23",
            ),
            self._doc(
                "SO TAY SINH VIEN 2025-2026.questions.md",
                "Question: So tay sinh vien 2025-2026 ap dung cho doi tuong nao? Answer: Sinh vien khoa 24.",
                {2025, 2026},
                "k24",
            ),
        )

    def _assert_top_source(self, query: str, expected_file: str) -> None:
        matches = _search_documents(self.docs, query, limit=3)
        self.assertTrue(matches)
        self.assertEqual(matches[0][1].path.name, expected_file)

    def test_year_2023_2024_query_hits_correct_handbook(self) -> None:
        self._assert_top_source(
            "So tay sinh vien 2023-2024 ap dung cho doi tuong nao?",
            "SO TAY SINH VIEN 2023-2024.questions.md",
        )

    def test_year_2024_2025_query_hits_correct_handbook(self) -> None:
        self._assert_top_source(
            "So tay sinh vien 2024-2025 ap dung cho doi tuong nao?",
            "SO TAY SINH VIEN 2024-2025.questions.md",
        )

    def test_year_2025_2026_query_hits_correct_handbook(self) -> None:
        self._assert_top_source(
            "So tay sinh vien 2025-2026 ap dung cho doi tuong nao?",
            "SO TAY SINH VIEN 2025-2026.questions.md",
        )


if __name__ == "__main__":
    unittest.main()
