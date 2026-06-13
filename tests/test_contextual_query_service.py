from __future__ import annotations

import unittest

from services.chat.contextual_query_service import (
    is_source_year_follow_up,
    rewrite_contextual_question,
    rewrite_follow_up_question,
)
from services.rag.ictu_scope_service import is_ictu_related_query


class ContextualQueryRewriteTests(unittest.TestCase):
    def test_rewrites_academic_year_follow_up(self) -> None:
        rewritten = rewrite_follow_up_question(
            "khóa 2024-2025 cần bao nhiêu tín chỉ để tốt nghiệp cử nhân?",
            "thế còn khóa 2025-2026 thì sao?",
        )

        self.assertEqual(
            rewritten,
            "Khóa 2025-2026 cần bao nhiêu tín chỉ để tốt nghiệp cử nhân?",
        )
        self.assertTrue(is_ictu_related_query(rewritten))

    def test_rewrites_foreign_language_certificate_follow_up(self) -> None:
        rewritten = rewrite_follow_up_question(
            "điều kiện tốt nghiệp của sinh viên ICTU là gì?",
            "còn chứng chỉ ngoại ngữ thì sao?",
        )

        self.assertEqual(
            rewritten,
            "Điều kiện chứng chỉ ngoại ngữ để tốt nghiệp của sinh viên ICTU là gì?",
        )
        self.assertTrue(is_ictu_related_query(rewritten))

    def test_rewrites_conduct_score_scholarship_follow_up(self) -> None:
        rewritten = rewrite_follow_up_question(
            "học bổng cần điều kiện gì?",
            "điểm rèn luyện thì sao?",
        )

        self.assertEqual(
            rewritten,
            "Điểm rèn luyện cần đạt điều kiện gì để xét học bổng?",
        )
        self.assertTrue(is_ictu_related_query(rewritten))

    def test_rewrites_short_year_and_next_year_variants(self) -> None:
        previous = "khóa 2024-2025 cần bao nhiêu tín chỉ để tốt nghiệp cử nhân?"

        self.assertEqual(
            rewrite_follow_up_question(previous, "còn 2025-2026?"),
            "Khóa 2025-2026 cần bao nhiêu tín chỉ để tốt nghiệp cử nhân?",
        )
        self.assertEqual(
            rewrite_follow_up_question(previous, "vậy khóa sau thì sao?"),
            "Khóa 2025-2026 cần bao nhiêu tín chỉ để tốt nghiệp cử nhân?",
        )

    def test_rewrites_major_follow_up_without_losing_previous_question(self) -> None:
        rewritten = rewrite_follow_up_question(
            "khóa 2024-2025 cần bao nhiêu tín chỉ để tốt nghiệp cử nhân?",
            "thế còn ngành CNTT thì sao?",
        )

        self.assertEqual(
            rewritten,
            "Đối với ngành CNTT, khóa 2024-2025 cần bao nhiêu tín chỉ để tốt nghiệp cử nhân?",
        )

    def test_does_not_rewrite_unrelated_short_question(self) -> None:
        rewritten = rewrite_contextual_question(
            "giá bitcoin?",
            [{"role": "user", "content": "học phí ICTU là bao nhiêu?"}],
        )

        self.assertEqual(rewritten, "giá bitcoin?")

    def test_uses_previous_rewritten_question_for_multi_hop_follow_up(self) -> None:
        rewritten = rewrite_contextual_question(
            "còn 2026-2027?",
            [
                {
                    "role": "user",
                    "content": "thế còn khóa 2025-2026 thì sao?",
                    "rewritten_question": "Khóa 2025-2026 cần bao nhiêu tín chỉ để tốt nghiệp cử nhân?",
                }
            ],
        )

        self.assertEqual(
            rewritten,
            "Khóa 2026-2027 cần bao nhiêu tín chỉ để tốt nghiệp cử nhân?",
        )

    def test_rewrites_source_year_reference_follow_up(self) -> None:
        current = "phần này là của năm bao nhiêu"

        self.assertTrue(is_source_year_follow_up(current))
        self.assertEqual(
            rewrite_follow_up_question("Khi nào sinh viên bị cảnh báo học tập?", current),
            "Nội dung trả lời cho câu hỏi 'khi nào sinh viên bị cảnh báo học tập' thuộc tài liệu năm học nào?",
        )


if __name__ == "__main__":
    unittest.main()
