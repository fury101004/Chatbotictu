from __future__ import annotations

import unicodedata
import unittest

from services.chat.multilingual_service import _build_final_prompt


def _ascii(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


class PromptBuilderTests(unittest.TestCase):
    def test_vietnamese_prompt_uses_single_contract_with_scope_and_fallback(self) -> None:
        prompt = _build_final_prompt(
            system_prompt="BASE SYSTEM PROMPT",
            current_lang="vi",
            safe_context="Thong tin hoc phi nam 2025.",
            user_question="Hoc phi ap dung the nao?",
            rag_tool="school_policy_rag",
        )
        prompt_ascii = _ascii(prompt)

        self.assertIn("BASE SYSTEM PROMPT", prompt)
        self.assertIn("LUAT CHO LUOT HIEN TAI:", prompt_ascii)
        self.assertIn("Pham vi tri thuc hien tai:", prompt_ascii)
        self.assertIn("ngu canh hien tai ben duoi", prompt_ascii)
        self.assertIn("Neu cau hoi thieu moc phan biet bat buoc", prompt_ascii)
        self.assertIn("Khong neu ten nguon, ten file, route, tool", prompt_ascii)
        self.assertIn('"Thong tin nay hien chua co trong tai lieu cua em."', prompt_ascii)

    def test_english_prompt_uses_single_contract_with_scope_and_fallback(self) -> None:
        prompt = _build_final_prompt(
            system_prompt="BASE SYSTEM PROMPT",
            current_lang="en",
            safe_context="Student email instructions.",
            user_question="How do I reactivate my student email?",
            rag_tool="student_faq_rag",
        )
        prompt_ascii = _ascii(prompt)

        self.assertIn("TURN RULES:", prompt)
        self.assertIn("Current knowledge scope: FAQ sinh vien.", prompt_ascii)
        self.assertIn("Only answer from the current context below.", prompt)
        self.assertIn("ask exactly one short clarification question instead of guessing", prompt)
        self.assertIn("Do not mention sources, filenames, routes, tool names", prompt)
        self.assertIn('"This information is not currently available in my documents."', prompt)

    def test_student_handbook_prompt_uses_required_no_info_reply(self) -> None:
        prompt = _build_final_prompt(
            system_prompt="BASE SYSTEM PROMPT",
            current_lang="vi",
            safe_context="Không có ngữ cảnh liên quan.",
            user_question="Thông tin không tồn tại trong sổ tay?",
            rag_tool="student_handbook_rag",
        )

        self.assertIn('"Không tìm thấy thông tin này trong sổ tay sinh viên."', prompt)


if __name__ == "__main__":
    unittest.main()
