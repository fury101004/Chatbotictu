from __future__ import annotations

import unittest

from services.rag.ictu_scope_service import is_ictu_related_query


class ICTUScopeServiceTests(unittest.TestCase):
    def test_detects_explicit_ictu_queries(self) -> None:
        self.assertTrue(is_ictu_related_query("ICTU co quy dinh hoc phi the nao?"))
        self.assertTrue(
            is_ictu_related_query(
                "Dai hoc Cong nghe Thong tin va Truyen thong Thai Nguyen o dau?"
            )
        )

    def test_detects_student_context_queries_without_school_name(self) -> None:
        self.assertTrue(is_ictu_related_query("Nam dau tien hoc bao nhieu tin chi?"))
        self.assertTrue(is_ictu_related_query("Em can dong BHYT dot nao?"))
        self.assertTrue(
            is_ictu_related_query(
                "Dieu kien dat danh hieu nguoi hoc Kha, Gioi, Xuat sac la gi?"
            )
        )

    def test_blocks_unrelated_queries(self) -> None:
        self.assertFalse(is_ictu_related_query("Thoi tiet Ha Noi hom nay the nao?"))
        self.assertFalse(is_ictu_related_query("Gia Bitcoin hien tai la bao nhieu?"))


if __name__ == "__main__":
    unittest.main()

