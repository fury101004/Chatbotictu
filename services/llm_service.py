from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

from services.rate_limit_monitor import record_429

load_dotenv()

PRIMARY_MODEL_NAME = "llama-3.1-8b-instant"
GROQ_FALLBACK_MODELS = [
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3-32b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
]
MODEL_NAME = PRIMARY_MODEL_NAME
DEFAULT_GROQ_MODEL_ORDER = [PRIMARY_MODEL_NAME, *GROQ_FALLBACK_MODELS]
DEFAULT_OLLAMA_MODEL_ORDER = ["llama3.1:8b"]
DEFAULT_PROVIDER_ORDER = ["groq", "ollama"]
DEFAULT_MODEL_ROTATION = "round_robin"
DISABLED_MODEL_ROTATION_VALUES = {"0", "false", "fixed", "no", "none", "off", "single"}
MODEL_DISPLAY_NAMES = {
    "groq:llama-3.1-8b-instant": "Groq Llama 3.1 8B Instant",
    "groq:llama-3.3-70b-versatile": "Groq Llama 3.3 70B Versatile",
    "groq:openai/gpt-oss-20b": "Groq GPT OSS 20B",
    "groq:openai/gpt-oss-120b": "Groq GPT OSS 120B",
    "groq:qwen/qwen3-32b": "Groq Qwen 3 32B",
    "groq:meta-llama/llama-4-scout-17b-16e-instruct": "Groq Llama 4 Scout 17B 16E",
}
_MODEL_ROTATION_LOCK = Lock()
_MODEL_ROTATION_INDEX = 0


@dataclass(slots=True)
class LLMResponse:
    text: str

    def __iter__(self):
        yield self


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    provider: str
    model: str

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"


def _split_env_list(value: str, default: list[str]) -> list[str]:
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or default


def _provider_order() -> list[str]:
    return [
        provider.lower()
        for provider in _split_env_list(os.getenv("LLM_PROVIDER_ORDER", ""), DEFAULT_PROVIDER_ORDER)
    ]


def _groq_models() -> list[str]:
    return _split_env_list(os.getenv("GROQ_MODEL_ORDER", ""), DEFAULT_GROQ_MODEL_ORDER)


def _ollama_models() -> list[str]:
    configured = os.getenv("OLLAMA_MODEL_ORDER", "").strip() or os.getenv("OLLAMA_MODEL", "").strip()
    return _split_env_list(configured, DEFAULT_OLLAMA_MODEL_ORDER)


def _groq_api_key() -> str:
    return os.getenv("GROQ_API_KEY", "").strip()


def _groq_base_url() -> str:
    return os.getenv("GROQ_API_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")


def _ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")


def model_rotation_mode() -> str:
    value = os.getenv("LLM_MODEL_ROTATION", DEFAULT_MODEL_ROTATION).strip().lower()
    if value in DISABLED_MODEL_ROTATION_VALUES:
        return "fixed"
    return "round_robin"


def _model_candidates(preferred_model: str = PRIMARY_MODEL_NAME) -> list[ModelCandidate]:
    candidates: list[ModelCandidate] = []
    for provider in _provider_order():
        if provider == "groq":
            if not _groq_api_key():
                continue
            models = _groq_models()
            if preferred_model and preferred_model in models:
                models = [preferred_model, *[model for model in models if model != preferred_model]]
            candidates.extend(ModelCandidate("groq", model) for model in models)
        elif provider == "ollama":
            candidates.extend(ModelCandidate("ollama", model) for model in _ollama_models())
    return candidates


def _rotate_candidates(candidates: list[ModelCandidate]) -> list[ModelCandidate]:
    if len(candidates) <= 1:
        return candidates

    primary_provider = candidates[0].provider
    rotatable = [candidate for candidate in candidates if candidate.provider == primary_provider]
    fallbacks = [candidate for candidate in candidates if candidate.provider != primary_provider]
    if len(rotatable) <= 1:
        return candidates

    global _MODEL_ROTATION_INDEX
    with _MODEL_ROTATION_LOCK:
        start = _MODEL_ROTATION_INDEX % len(rotatable)
        _MODEL_ROTATION_INDEX += 1

    return [*rotatable[start:], *rotatable[:start], *fallbacks]


def model_display_name(value: str | ModelCandidate) -> str:
    if isinstance(value, ModelCandidate):
        label = value.label
    else:
        label = value

    if label in MODEL_DISPLAY_NAMES:
        return MODEL_DISPLAY_NAMES[label]
    if ":" not in label:
        return label

    provider, model = label.split(":", 1)
    readable_model = model.replace("/", " ").replace("-", " ").replace("_", " ")
    return f"{provider.title()} {readable_model.title()}".strip()


def get_configured_model_labels() -> list[str]:
    candidates = _model_candidates()
    if not candidates:
        return []
    primary_provider = candidates[0].provider
    return [
        model_display_name(candidate)
        for candidate in candidates
        if candidate.provider == primary_provider
    ]


def get_chat_model_options() -> list[dict[str, str]]:
    candidates = _model_candidates()
    if not candidates:
        return []

    primary_provider = candidates[0].provider
    return [
        {"value": candidate.model, "label": model_display_name(candidate)}
        for candidate in candidates
        if candidate.provider == primary_provider
    ]


def resolve_model_choice(value: Optional[str]) -> tuple[str, bool]:
    selected = (value or "").strip()
    if selected.lower() in {"", "auto", "round_robin"}:
        return PRIMARY_MODEL_NAME, True

    for candidate in _model_candidates():
        if selected in {candidate.model, candidate.label}:
            return candidate.model, False

    return PRIMARY_MODEL_NAME, True


@lru_cache(maxsize=8)
def get_model(model_name: str = PRIMARY_MODEL_NAME) -> Optional[ModelCandidate]:
    candidates = _model_candidates(model_name)
    return candidates[0] if candidates else None


def llm_network_available(timeout: float = 0.75) -> bool:
    for candidate in _model_candidates():
        if candidate.provider == "groq":
            parsed = urlparse(_groq_base_url())
            host = parsed.hostname or "api.groq.com"
            port = parsed.port or 443
        elif candidate.provider == "ollama":
            parsed = urlparse(_ollama_base_url())
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 11434
        else:
            continue

        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError as exc:
            print(f"LLM backend {candidate.label} unavailable, trying next backend: {exc}")
    return False


def _message_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_message_content(item) for item in value)
    if isinstance(value, dict):
        if "text" in value:
            return str(value["text"])
        if "content" in value:
            return _message_content(value["content"])
    return str(value)


def _to_chat_messages(contents: Any) -> list[dict[str, str]]:
    if isinstance(contents, str):
        return [{"role": "user", "content": contents}]

    if isinstance(contents, list):
        messages: list[dict[str, str]] = []
        for item in contents:
            if not isinstance(item, dict):
                messages.append({"role": "user", "content": _message_content(item)})
                continue

            role = str(item.get("role", "user")).lower()
            if role == "model":
                role = "assistant"
            if role not in {"system", "user", "assistant"}:
                role = "user"

            if "parts" in item:
                content = _message_content(item["parts"])
            else:
                content = _message_content(item.get("content", ""))
            if content.strip():
                messages.append({"role": role, "content": content})
        if messages:
            return messages

    return [{"role": "user", "content": _message_content(contents)}]


def _timeout_seconds(request_options: Optional[dict]) -> float:
    if not request_options:
        return 90.0
    try:
        return float(request_options.get("timeout", 90))
    except (TypeError, ValueError):
        return 90.0


def _generation_options(generation_config: Optional[dict]) -> dict[str, Any]:
    generation_config = generation_config or {}
    options: dict[str, Any] = {}
    if "temperature" in generation_config:
        options["temperature"] = generation_config["temperature"]
    if "top_p" in generation_config:
        options["top_p"] = generation_config["top_p"]
    if "max_output_tokens" in generation_config:
        options["max_tokens"] = generation_config["max_output_tokens"]
    elif "max_tokens" in generation_config:
        options["max_tokens"] = generation_config["max_tokens"]
    if generation_config.get("response_mime_type") == "application/json":
        options["response_format"] = {"type": "json_object"}
    return options


def _is_rate_limited_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return exc.response.status_code == 429

    normalized = str(exc).casefold()
    return "429" in normalized or "rate limit" in normalized or "too many requests" in normalized


def _call_groq(
    *,
    model: str,
    messages: list[dict[str, str]],
    generation_config: Optional[dict],
    request_options: Optional[dict],
) -> LLMResponse:
    options = _generation_options(generation_config)
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if "max_tokens" in options:
        payload["max_completion_tokens"] = options.pop("max_tokens")
    payload.update(options)

    response = httpx.post(
        f"{_groq_base_url()}/chat/completions",
        headers={
            "Authorization": f"Bearer {_groq_api_key()}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=_timeout_seconds(request_options),
    )
    response.raise_for_status()
    data = response.json()
    text = data["choices"][0]["message"].get("content") or ""
    return LLMResponse(text=text.strip())


def _call_ollama(
    *,
    model: str,
    messages: list[dict[str, str]],
    generation_config: Optional[dict],
    request_options: Optional[dict],
) -> LLMResponse:
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
        f"{_ollama_base_url()}/api/chat",
        json=payload,
        timeout=_timeout_seconds(request_options),
    )
    response.raise_for_status()
    data = response.json()
    text = (data.get("message") or {}).get("content") or data.get("response") or ""
    return LLMResponse(text=text.strip())


def generate_content_with_fallback(
    contents: Any,
    *,
    generation_config: Optional[dict] = None,
    safety_settings: Optional[list[dict]] = None,
    request_options: Optional[dict] = None,
    stream: bool = False,
    preferred_model: str = PRIMARY_MODEL_NAME,
    rotate: bool = True,
) -> tuple[LLMResponse, str]:
    del safety_settings, stream
    messages = _to_chat_messages(contents)
    errors: list[str] = []
    candidates = _model_candidates(preferred_model)
    if rotate and model_rotation_mode() == "round_robin":
        candidates = _rotate_candidates(candidates)

    for candidate in candidates:
        try:
            if candidate.provider == "groq":
                response = _call_groq(
                    model=candidate.model,
                    messages=messages,
                    generation_config=generation_config,
                    request_options=request_options,
                )
            elif candidate.provider == "ollama":
                response = _call_ollama(
                    model=candidate.model,
                    messages=messages,
                    generation_config=generation_config,
                    request_options=request_options,
                )
            else:
                continue
            return response, candidate.label
        except Exception as exc:
            if _is_rate_limited_error(exc):
                record_429(
                    "llm_provider",
                    detail=str(exc),
                    metadata={"model": candidate.label},
                )
            errors.append(f"{candidate.label}: {exc}")
            print(f"LLM backend {candidate.label} failed, trying fallback: {exc}")

    if not errors:
        raise RuntimeError("No LLM backend is configured. Set GROQ_API_KEY or configure Ollama.")
    raise RuntimeError("All LLM backends failed: " + " | ".join(errors))
