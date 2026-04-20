from __future__ import annotations

import unittest
from unittest.mock import patch

from services.web_search import search_web_ictu


class WebSearchServiceTests(unittest.TestCase):
    def test_search_prioritizes_ictu_official_site_then_broader_results(self) -> None:
        official_results = [
            {
                "url": "https://ictu.edu.vn/thong-bao-moi",
                "title": "Thông báo mới ICTU",
                "content": "Nội dung thông báo của ICTU.",
            }
        ]
        broader_results = [
            {
                "url": "https://tuyensinh.tnu.edu.vn/ictu",
                "title": "ICTU tuyển sinh",
                "content": "Thông tin liên quan Trường Đại học Công nghệ Thông tin và Truyền thông.",
            }
        ]

        with (
            patch("services.web_search._search_base_url", return_value="https://search.local"),
            patch("services.web_search._extract_text", return_value=""),
            patch("services.web_search._search_raw", side_effect=[official_results, broader_results]) as search_raw,
        ):
            docs = search_web_ictu("học phí mới nhất", limit=3)

        self.assertIn("site:ictu.edu.vn", search_raw.call_args_list[0].args[0])
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].url, "https://ictu.edu.vn/thong-bao-moi")
        self.assertEqual(docs[1].url, "https://tuyensinh.tnu.edu.vn/ictu")

    def test_search_skips_unrelated_queries(self) -> None:
        with (
            patch("services.web_search._search_base_url", return_value="https://search.local"),
            patch("services.web_search._search_raw") as search_raw,
        ):
            docs = search_web_ictu("giá Bitcoin hôm nay", limit=3)

        self.assertEqual(docs, [])
        search_raw.assert_not_called()


if __name__ == "__main__":
    unittest.main()
