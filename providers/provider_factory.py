from __future__ import annotations

from providers.base_llm_provider import BaseLLMProvider
from providers.gemini_provider import GeminiProvider
from providers.groq_provider import GroqProvider
from providers.ollama_provider import OllamaProvider
from providers.openai_provider import OpenAIProvider


def create_llm_providers() -> dict[str, BaseLLMProvider]:
    return {
        "groq": GroqProvider(),
        "openai": OpenAIProvider(),
        "ollama": OllamaProvider(),
        "gemini": GeminiProvider(),
    }
