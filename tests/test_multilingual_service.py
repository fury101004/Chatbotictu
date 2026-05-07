from __future__ import annotations

import unittest

from services.chat.multilingual_service import _sanitize_model_reply


class MultilingualServiceTests(unittest.TestCase):
    def test_sanitize_model_reply_removes_think_block(self) -> None:
        raw = "<think>internal reasoning</think>\n\nTra loi hop le."
        self.assertEqual(_sanitize_model_reply(raw), "Tra loi hop le.")

    def test_sanitize_model_reply_keeps_regular_answer(self) -> None:
        raw = "Tra loi ngan gon va dung trong tai lieu."
        self.assertEqual(_sanitize_model_reply(raw), raw)


if __name__ == "__main__":
    unittest.main()

