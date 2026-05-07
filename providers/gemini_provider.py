from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Optional

from providers.base_llm_provider import BaseLLMProvider, ModelCandidate, ProviderResponse


class GeminiProvider(BaseLLMProvider):
    name = "gemini"
    primary_model_name = "gemini-2.5-flash"
    fallback_model_name = "gemini-2.5-flash-lite"
    safety_settings = [
        {"category": category, "threshold": "BLOCK_NONE"}
        for category in [
            "HARM_CATEGORY_HARASSMENT",
            "HARM_CATEGORY_HATE_SPEECH",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT",
            "HARM_CATEGORY_DANGEROUS_CONTENT",
        ]
    ]
    default_generation_config = {
        "temperature": 0.1,
        "max_output_tokens": 800,
        "top_p": 0.9,
    }

    @staticmethod
    @lru_cache(maxsize=1)
    def _import_genai():
        import google.generativeai as genai

        return genai

    @classmethod
    @lru_cache(maxsize=4)
    def get_model(cls, model_name: str = "gemini-2.5-flash") -> Optional[Any]:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            print("GEMINI_API_KEY is missing; Gemini responses are disabled until it is configured.")
            return None

        genai = cls._import_genai()
        genai.configure(api_key=api_key)
        return genai.GenerativeModel(
            model_name,
            safety_settings=cls.safety_settings,
            generation_config=cls.default_generation_config,
        )

    @staticmethod
    def looks_like_quota_error(exc: Exception) -> bool:
        message = f"{type(exc).__name__}: {exc}".lower()
        status_markers = [
            " 400",
            "status code 400",
            "(400)",
            "badrequest",
            " 429",
            "status code 429",
            "(429)",
            "resource exhausted",
            "resourceexhausted",
            "too many requests",
        ]
        quota_markers = [
            "free tier",
            "quota",
            "rate limit",
            "billing",
            "resource exhausted",
            "resourceexhausted",
            "exceeded",
            "too many requests",
        ]
        return any(marker in message for marker in status_markers) and any(
            marker in message for marker in quota_markers
        )

    def available(self) -> bool:
        return self.get_model(self.primary_model_name) is not None

    def list_models(self, configured_models: list[str], *, preferred_model: Optional[str] = None) -> list[ModelCandidate]:
        if not os.getenv("GEMINI_API_KEY", "").strip():
            return []
        models = list(configured_models)
        if preferred_model and preferred_model in models:
            models = [preferred_model, *[model for model in models if model != preferred_model]]
        return [ModelCandidate(self.name, model) for model in models]

    def invoke(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        generation_config: Optional[dict],
        request_options: Optional[dict],
    ) -> ProviderResponse:
        llm = self.get_model(model)
        if llm is None:
            raise RuntimeError("Gemini model is not configured.")
        response = llm.generate_content(
            messages,
            generation_config=generation_config,
            request_options=request_options,
        )
        return ProviderResponse(text=str(getattr(response, "text", "") or "").strip())
