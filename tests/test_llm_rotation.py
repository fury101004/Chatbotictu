from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import services.llm_service as llm_service


class LLMRotationTests(unittest.TestCase):
    def setUp(self) -> None:
        llm_service.get_model.cache_clear()
        llm_service._MODEL_ROTATION_INDEX = 0

    def tearDown(self) -> None:
        llm_service.get_model.cache_clear()
        llm_service._MODEL_ROTATION_INDEX = 0

    @patch.dict(
        os.environ,
        {
            "GROQ_API_KEY": "test-key",
            "GROQ_MODEL_ORDER": "model-a,model-b,model-c",
            "LLM_PROVIDER_ORDER": "groq",
        },
        clear=True,
    )
    def test_round_robin_rotates_successful_calls(self) -> None:
        def fake_call_groq(**kwargs):
            return llm_service.LLMResponse(text=kwargs["model"])

        with patch("services.llm_service._call_groq", side_effect=fake_call_groq):
            used_models = [
                llm_service.generate_content_with_fallback("hello")[1]
                for _ in range(4)
            ]

        self.assertEqual(
            used_models,
            [
                "groq:model-a",
                "groq:model-b",
                "groq:model-c",
                "groq:model-a",
            ],
        )

    @patch.dict(
        os.environ,
        {
            "GROQ_API_KEY": "test-key",
            "GROQ_MODEL_ORDER": "model-a,model-b,model-c",
            "LLM_PROVIDER_ORDER": "groq",
        },
        clear=True,
    )
    def test_rotated_candidate_falls_back_to_next_model(self) -> None:
        llm_service._MODEL_ROTATION_INDEX = 1

        def fake_call_groq(**kwargs):
            if kwargs["model"] == "model-b":
                raise RuntimeError("model-b unavailable")
            return llm_service.LLMResponse(text=kwargs["model"])

        with patch("services.llm_service._call_groq", side_effect=fake_call_groq):
            response, used_model = llm_service.generate_content_with_fallback("hello")

        self.assertEqual(response.text, "model-c")
        self.assertEqual(used_model, "groq:model-c")

    @patch.dict(
        os.environ,
        {
            "GROQ_API_KEY": "test-key",
            "GROQ_MODEL_ORDER": "model-a,model-b,model-c",
            "LLM_PROVIDER_ORDER": "groq",
        },
        clear=True,
    )
    def test_rotate_false_keeps_primary_candidate_first(self) -> None:
        def fake_call_groq(**kwargs):
            return llm_service.LLMResponse(text=kwargs["model"])

        with patch("services.llm_service._call_groq", side_effect=fake_call_groq):
            used_models = [
                llm_service.generate_content_with_fallback("hello", rotate=False)[1]
                for _ in range(3)
            ]

        self.assertEqual(used_models, ["groq:model-a", "groq:model-a", "groq:model-a"])

    @patch.dict(
        os.environ,
        {
            "GROQ_API_KEY": "test-key",
            "GROQ_MODEL_ORDER": "model-a,model-b",
            "LLM_PROVIDER_ORDER": "groq,ollama",
            "OLLAMA_MODEL_ORDER": "local-model",
        },
        clear=True,
    )
    def test_rotation_keeps_secondary_provider_as_fallback(self) -> None:
        def fake_call_groq(**kwargs):
            return llm_service.LLMResponse(text=kwargs["model"])

        with (
            patch("services.llm_service._call_groq", side_effect=fake_call_groq),
            patch("services.llm_service._call_ollama") as call_ollama,
        ):
            used_models = [
                llm_service.generate_content_with_fallback("hello")[1]
                for _ in range(3)
            ]

        self.assertEqual(used_models, ["groq:model-a", "groq:model-b", "groq:model-a"])
        call_ollama.assert_not_called()

    @patch.dict(
        os.environ,
        {
            "GROQ_API_KEY": "test-key",
            "GROQ_MODEL_ORDER": "model-a,model-b",
            "LLM_MODEL_ROTATION": "fixed",
            "LLM_PROVIDER_ORDER": "groq",
        },
        clear=True,
    )
    def test_env_can_disable_rotation(self) -> None:
        def fake_call_groq(**kwargs):
            return llm_service.LLMResponse(text=kwargs["model"])

        with patch("services.llm_service._call_groq", side_effect=fake_call_groq):
            used_models = [
                llm_service.generate_content_with_fallback("hello")[1]
                for _ in range(3)
            ]

        self.assertEqual(used_models, ["groq:model-a", "groq:model-a", "groq:model-a"])
        self.assertEqual(llm_service.model_rotation_mode(), "fixed")

    @patch.dict(
        os.environ,
        {
            "GROQ_API_KEY": "test-key",
            "GROQ_MODEL_ORDER": "model-a,model-b",
            "LLM_PROVIDER_ORDER": "groq",
        },
        clear=True,
    )
    def test_resolves_specific_model_choice(self) -> None:
        self.assertEqual(llm_service.resolve_model_choice("model-b"), ("model-b", False))
        self.assertEqual(llm_service.resolve_model_choice("groq:model-b"), ("model-b", False))
        self.assertEqual(llm_service.resolve_model_choice("auto"), (llm_service.PRIMARY_MODEL_NAME, True))
        self.assertEqual(llm_service.resolve_model_choice("unknown"), (llm_service.PRIMARY_MODEL_NAME, True))

        self.assertEqual(
            llm_service.get_chat_model_options(),
            [
                {"value": "model-a", "label": "Groq Model A"},
                {"value": "model-b", "label": "Groq Model B"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
