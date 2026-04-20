from __future__ import annotations

import unittest

from services.ictu_scope_service import is_ictu_related_query


class ICTUScopeServiceTests(unittest.TestCase):
    def test_detects_explicit_ictu_queries(self) -> None:
        self.assertTrue(is_ictu_related_query("ICTU có quy định học phí thế nào?"))
        self.assertTrue(is_ictu_related_query("Đại học Công nghệ Thông tin và Truyền thông Thái Nguyên ở đâu?"))

    def test_detects_student_context_queries_without_school_name(self) -> None:
        self.assertTrue(is_ictu_related_query("Năm đầu tiên học bao nhiêu tín chỉ?"))
        self.assertTrue(is_ictu_related_query("Em cần đóng BHYT đợt nào?"))

    def test_blocks_unrelated_queries(self) -> None:
        self.assertFalse(is_ictu_related_query("Thời tiết Hà Nội hôm nay thế nào?"))
        self.assertFalse(is_ictu_related_query("Giá Bitcoin hiện tại là bao nhiêu?"))


if __name__ == "__main__":
    unittest.main()
