"""LLM access helpers with a LangChain-first Ollama integration."""

from __future__ import annotations

from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

import requests

from config import OLLAMA_MODEL, OLLAMA_URL


class _RequestsOllamaClient:
    def invoke(self, prompt: str) -> str:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
            },
            timeout=90,
        )
        response.raise_for_status()
        return response.json().get("response", "").strip()


def _ollama_base_url() -> str:
    parsed = urlparse(OLLAMA_URL)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return "http://127.0.0.1:11434"


@lru_cache(maxsize=1)
def get_llm() -> Any:
    try:
        try:
            from langchain_community.llms import Ollama
        except Exception:
            from langchain_community.llms.ollama import Ollama

        return Ollama(base_url=_ollama_base_url(), model=OLLAMA_MODEL, temperature=0)
    except Exception:
        return _RequestsOllamaClient()


def invoke_llm(prompt: str) -> str:
    result = get_llm().invoke(prompt)

    if isinstance(result, str):
        return result.strip()

    content = getattr(result, "content", "")
    return str(content).strip()
