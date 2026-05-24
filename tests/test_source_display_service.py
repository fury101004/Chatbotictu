from __future__ import annotations

import unittest

from services.rag.source_display_service import build_source_details, format_source_label


class SourceDisplayServiceTests(unittest.TestCase):
    def test_formats_handbook_question_source_as_friendly_label(self) -> None:
        label = format_source_label("student_handbooks/5. SO TAY SINH VIEN 2022-2023.questions.md")

        self.assertEqual(label, "Sổ tay sinh viên 2022-2023 (hỏi đáp trích xuất)")

    def test_formats_handbook_raw_source_as_full_document_label(self) -> None:
        label = format_source_label("student_handbooks/8. SO TAY SINH VIEN 2025-2026.md")

        self.assertEqual(label, "Sổ tay sinh viên 2025-2026 (bản đầy đủ)")

    def test_build_source_details_keeps_raw_source_for_links(self) -> None:
        details = build_source_details(
            [
                "student_handbooks/5. SO TAY SINH VIEN 2022-2023.questions.md",
                "student_handbooks/5. SO TAY SINH VIEN 2022-2023.questions.md",
                "BOT_RULE",
            ]
        )

        self.assertEqual(
            details,
            [
                {
                    "source": "student_handbooks/5. SO TAY SINH VIEN 2022-2023.questions.md",
                    "label": "Sổ tay sinh viên 2022-2023 (hỏi đáp trích xuất)",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
