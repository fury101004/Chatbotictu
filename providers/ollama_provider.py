from __future__ import annotations

import os
from typing import Any, Optional

import httpx

from providers.base_llm_provider import BaseLLMProvider, ModelCandidate, ProviderResponse


class OllamaProvider(BaseLLMProvider):
    name = "ollama"

    def base_url(self) -> str:
        return os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")

    def available(self) -> bool:
        return True

    def list_models(self, configured_models: list[str], *, preferred_model: Optional[str] = None) -> list[ModelCandidate]:
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
        options: dict[str, Any] = {}
        if "temperature" in generation_config:
            options["temperature"] = generation_config["temperature"]
        if "top_p" in generation_config:
            options["top_p"] = generation_config["top_p"]
        if "max_output_tokens" in generation_config:
            options["num_predict"] = generation_config["max_output_tokens"]

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        if generation_config.get("response_mime_type") == "application/json":
            payload["format"] = "json"
        response = httpx.post(
            f"{self.base_url()}/api/chat",
            json=payload,
            timeout=_timeout_seconds(request_options),
        )
        response.raise_for_status()
        data = response.json()
        text = (data.get("message") or {}).get("content") or data.get("response") or ""
        return ProviderResponse(text=text.strip())


def _timeout_seconds(request_options: Optional[dict]) -> float:
    if not request_options:
        return 90.0
    try:
        return float(request_options.get("timeout", 90))
    except (TypeError, ValueError):
        return 90.0
