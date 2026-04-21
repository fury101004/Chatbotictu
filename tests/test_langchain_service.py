from __future__ import annotations

import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from services.langchain_service import invoke_json_prompt_chain, invoke_text_prompt_chain
from services.llm_service import LLMResponse


class LangChainServiceTests(unittest.TestCase):
    def test_text_prompt_chain_formats_history_and_returns_used_model(self) -> None:
        prompt = ChatPromptTemplate.from_messages(
            [
                MessagesPlaceholder("history"),
                ("user", "{prompt}"),
            ]
        )

        with patch(
            "services.langchain_service.generate_content_with_fallback",
            return_value=(LLMResponse(text="Chain reply"), "groq:test-model"),
        ) as generate_mock:
            reply, used_model = invoke_text_prompt_chain(
                prompt,
                {
                    "history": [
                        HumanMessage(content="Xin chao"),
                        AIMessage(content="Chao ban"),
                    ],
                    "prompt": "Tra loi cau hoi nay",
                },
            )

        self.assertEqual(reply, "Chain reply")
        self.assertEqual(used_model, "groq:test-model")
        sent_messages = generate_mock.call_args.args[0]
        self.assertEqual(
            sent_messages,
            [
                {"role": "user", "content": "Xin chao"},
                {"role": "assistant", "content": "Chao ban"},
                {"role": "user", "content": "Tra loi cau hoi nay"},
            ],
        )

    def test_json_prompt_chain_parses_json_output(self) -> None:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "Return JSON only"),
                ("user", "{question}"),
            ]
        )

        with patch(
            "services.langchain_service.generate_content_with_fallback",
            return_value=(
                LLMResponse(text='{"tool":"student_faq_rag","confidence":0.91}'),
                "groq:test-model",
            ),
        ):
            payload, raw_text, used_model = invoke_json_prompt_chain(
                prompt,
                {"question": "Tool nao phu hop?"},
            )

        self.assertEqual(payload, {"tool": "student_faq_rag", "confidence": 0.91})
        self.assertEqual(raw_text, '{"tool":"student_faq_rag","confidence":0.91}')
        self.assertEqual(used_model, "groq:test-model")


if __name__ == "__main__":
    unittest.main()
