from __future__ import annotations

import os
from typing import Any, Optional

import httpx

from providers.base_llm_provider import BaseLLMProvider, ModelCandidate, ProviderResponse


class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def api_key(self) -> str:
        return os.getenv("OPENAI_API_KEY", "").strip()

    def base_url(self) -> str:
        return os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    def available(self) -> bool:
        return bool(self.api_key())

    def list_models(self, configured_models: list[str], *, preferred_model: Optional[str] = None) -> list[ModelCandidate]:
        if not self.available():
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
        generation_config = generation_config or {}
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if "temperature" in generation_config:
            payload["temperature"] = generation_config["temperature"]
        if "top_p" in generation_config:
            payload["top_p"] = generation_config["top_p"]
        if "max_output_tokens" in generation_config:
            payload["max_tokens"] = generation_config["max_output_tokens"]
        elif "max_tokens" in generation_config:
            payload["max_tokens"] = generation_config["max_tokens"]
        if generation_config.get("response_mime_type") == "application/json":
            payload["response_format"] = {"type": "json_object"}

        response = httpx.post(
            f"{self.base_url()}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key()}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=_timeout_seconds(request_options),
        )
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"].get("content") or ""
        return ProviderResponse(text=text.strip())


def _timeout_seconds(request_options: Optional[dict]) -> float:
    if not request_options:
        return 90.0
    try:
        return float(request_options.get("timeout", 90))
    except (TypeError, ValueError):
        return 90.0
