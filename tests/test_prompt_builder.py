from __future__ import annotations

import unicodedata
import unittest

from services.multilingual_service import _build_final_prompt


def _ascii(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


class PromptBuilderTests(unittest.TestCase):
    def test_vietnamese_prompt_includes_policy_guidance_and_exact_fallback(self) -> None:
        prompt = _build_final_prompt(
            system_prompt="BASE SYSTEM PROMPT",
            current_lang="vi",
            safe_context="Thong tin hoc phi nam 2025.",
            user_question="Hoc phi ap dung the nao?",
            rag_tool="school_policy_rag",
        )
        prompt_ascii = _ascii(prompt)

        self.assertIn("BASE SYSTEM PROMPT", prompt)
        self.assertIn("Nhom tri thuc hien tai: Quy dinh va chinh sach.", prompt_ascii)
        self.assertIn("so van ban, nam", prompt_ascii)
        self.assertIn("ap dung", prompt_ascii)
        self.assertIn("thoi han hoac", prompt_ascii)
        self.assertIn("giai thich du chi tiet", prompt_ascii)
        self.assertIn("Khong tra loi cut lun", prompt_ascii)
        self.assertIn('"Thong tin nay hien chua co trong tai lieu cua em."', prompt_ascii)

    def test_english_prompt_uses_english_contract_and_faq_guidance(self) -> None:
        prompt = _build_final_prompt(
            system_prompt="BASE SYSTEM PROMPT",
            current_lang="en",
            safe_context="Student email instructions.",
            user_question="How do I reactivate my student email?",
            rag_tool="student_faq_rag",
        )
        prompt_ascii = _ascii(prompt)

        self.assertIn("TURN-SPECIFIC RULES:", prompt)
        self.assertIn("Current knowledge group: FAQ sinh vien.", prompt_ascii)
        self.assertIn("FAQ and operational guidance", prompt)
        self.assertIn("professional detail", prompt)
        self.assertIn('"This information is not currently available in my documents."', prompt)


if __name__ == "__main__":
    unittest.main()
