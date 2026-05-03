from __future__ import annotations

import unittest

from services.search_backends import searxng_service


class SearxngServiceTests(unittest.TestCase):
    def test_non_ictu_news_keywords_are_ignored(self) -> None:
        self.assertFalse(searxng_service._is_news_query("Tin tuc chien su Iran hom nay"))
        self.assertFalse(searxng_service._is_news_query("Breaking news Ukraine moi nhat"))

    def test_ictu_news_keywords_use_news_search(self) -> None:
        self.assertTrue(searxng_service._is_news_query("Tin tuc ICTU moi nhat hom nay"))
        self.assertTrue(searxng_service._is_news_query("ICTU co thong bao moi nao khong?"))

    def test_non_ictu_realtime_keywords_are_ignored(self) -> None:
        self.assertFalse(searxng_service._is_realtime_query("Thoi tiet hom nay the nao?"))
        self.assertFalse(searxng_service._is_realtime_query("Ty gia USD/VND hom nay bao nhieu?"))

    def test_ictu_dynamic_keywords_are_realtime_queries(self) -> None:
        self.assertTrue(searxng_service._is_realtime_query("ICTU tuyen sinh co nhung phuong thuc nao?"))
        self.assertTrue(searxng_service._is_realtime_query("Hoc phi ICTU ky nay la bao nhieu?"))
        self.assertTrue(searxng_service._is_realtime_query("Lich nhap hoc ICTU da co chua?"))

    def test_ictu_dynamic_keywords_require_ictu_context(self) -> None:
        self.assertFalse(searxng_service._is_realtime_query("Tuyen sinh dai hoc Y co phuong thuc nao?"))


if __name__ == "__main__":
    unittest.main()
