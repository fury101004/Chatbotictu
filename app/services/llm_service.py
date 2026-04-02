"""LLM access helpers supporting Ollama and Gemini with safe debug details."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any, Dict, List, Sequence

import requests

from app.core.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLM_PROVIDER,
    OLLAMA_MODEL,
    OLLAMA_URL,
    resolve_llm_provider,
)


logger = logging.getLogger(__name__)
_GEMINI_FALLBACK_MODELS: Sequence[str] = ("gemini-1.5-flash",)


def sanitize_debug_detail(value: str, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())

    if GEMINI_API_KEY:
        text = text.replace(GEMINI_API_KEY, "***")

    text = re.sub(r"AIza[0-9A-Za-z\-_]{12,}", "***", text)

    if len(text) > limit:
        text = f"{text[: limit - 3]}..."

    return text


class LLMInvocationError(RuntimeError):
    def __init__(
        self,
        *,
        provider: str,
        requested_model: str,
        attempted_models: Sequence[str] | None = None,
        detail: str = "",
        status_code: int | None = None,
    ) -> None:
        self.provider = provider
        self.requested_model = requested_model
        self.attempted_models = tuple(dict.fromkeys(attempted_models or [requested_model]))
        self.status_code = status_code
        self.detail = sanitize_debug_detail(detail)
        super().__init__(self.detail or f"{provider} invocation failed")

    def debug_summary(self) -> str:
        parts: List[str] = []

        if self.status_code is not None:
            parts.append(f"HTTP {self.status_code}")

        if self.attempted_models:
            parts.append(
                "Đã thử model: " + ", ".join(f"`{model}`" for model in self.attempted_models)
            )

        if self.detail:
            parts.append(self.detail)

        return ". ".join(parts).strip()


class _GeminiModelHttpError(RuntimeError):
    def __init__(self, *, model: str, status_code: int, detail: str) -> None:
        self.model = model
        self.status_code = status_code
        self.detail = sanitize_debug_detail(detail)
        super().__init__(self.detail or f"Gemini model {model} failed")


class _RequestsOllamaClient:
    def invoke(self, prompt: str) -> str:
        try:
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
        except requests.RequestException as exc:
            raise LLMInvocationError(
                provider="ollama",
                requested_model=OLLAMA_MODEL,
                detail=f"Lỗi gọi Ollama: {sanitize_debug_detail(str(exc))}",
                status_code=getattr(getattr(exc, "response", None), "status_code", None),
            ) from exc

        return response.json().get("response", "").strip()


class _RequestsGeminiClient:
    def __init__(self) -> None:
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY chưa được cấu hình.")

    def invoke(self, prompt: str) -> str:
        attempted_models: List[str] = []
        last_error: _GeminiModelHttpError | None = None

        for model_name in _gemini_model_candidates():
            attempted_models.append(model_name)

            try:
                text = self._invoke_single_model(model_name, prompt)
                if model_name != GEMINI_MODEL:
                    logger.warning(
                        "Gemini fallback activated: requested model=%s, active model=%s",
                        GEMINI_MODEL,
                        model_name,
                    )
                return text
            except _GeminiModelHttpError as exc:
                last_error = exc
                if _should_retry_gemini_model(exc.status_code, exc.detail):
                    logger.warning(
                        "Gemini model %s failed with HTTP %s, trying fallback if available.",
                        exc.model,
                        exc.status_code,
                    )
                    continue
                raise LLMInvocationError(
                    provider="gemini",
                    requested_model=GEMINI_MODEL,
                    attempted_models=attempted_models,
                    detail=_format_gemini_failure_detail(exc, attempted_models),
                    status_code=exc.status_code,
                ) from exc
            except requests.RequestException as exc:
                raise LLMInvocationError(
                    provider="gemini",
                    requested_model=GEMINI_MODEL,
                    attempted_models=attempted_models,
                    detail=f"Lỗi kết nối Gemini: {sanitize_debug_detail(str(exc))}",
                    status_code=getattr(getattr(exc, "response", None), "status_code", None),
                ) from exc

        if last_error is not None:
            raise LLMInvocationError(
                provider="gemini",
                requested_model=GEMINI_MODEL,
                attempted_models=attempted_models,
                detail=_format_gemini_failure_detail(last_error, attempted_models),
                status_code=last_error.status_code,
            ) from last_error

        raise LLMInvocationError(
            provider="gemini",
            requested_model=GEMINI_MODEL,
            attempted_models=attempted_models or [GEMINI_MODEL],
            detail="Không thể khởi tạo phiên gọi Gemini.",
        )

    def _invoke_single_model(self, model_name: str, prompt: str) -> str:
        response = requests.post(
            _gemini_endpoint(model_name),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": GEMINI_API_KEY,
            },
            json={
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt}],
                    }
                ],
                "generationConfig": {
                    "temperature": 0,
                },
            },
            timeout=90,
        )

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise _GeminiModelHttpError(
                model=model_name,
                status_code=response.status_code,
                detail=response.text,
            ) from exc

        text = _extract_gemini_text(response.json())
        if text:
            return text

        raise _GeminiModelHttpError(
            model=model_name,
            status_code=response.status_code,
            detail="Gemini API không trả về nội dung văn bản hợp lệ.",
        )


def _gemini_model_candidates() -> Sequence[str]:
    candidates = [GEMINI_MODEL.strip()]
    for fallback_model in _GEMINI_FALLBACK_MODELS:
        normalized = fallback_model.strip()
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    return tuple(candidates)


def _gemini_endpoint(model_name: str) -> str:
    resource_name = model_name.strip()
    if not resource_name.startswith("models/"):
        resource_name = f"models/{resource_name}"
    return f"https://generativelanguage.googleapis.com/v1beta/{resource_name}:generateContent"


def _should_retry_gemini_model(status_code: int, detail: str) -> bool:
    if status_code == 404:
        return True

    normalized = sanitize_debug_detail(detail).lower()
    model_keywords = ("model", "not found", "unsupported", "permission", "access", "available")

    return status_code in {400, 403} and any(keyword in normalized for keyword in model_keywords)


def _format_gemini_failure_detail(
    error: _GeminiModelHttpError,
    attempted_models: Sequence[str],
) -> str:
    attempted = ", ".join(f"`{model}`" for model in dict.fromkeys(attempted_models))
    base = f"Gemini model `{error.model}` trả về HTTP {error.status_code}."
    if attempted:
        base += f" Đã thử: {attempted}."
    if error.detail:
        base += f" Phản hồi: {error.detail}"
    return base


def _extract_gemini_text(payload: Dict[str, Any]) -> str:
    parts: List[str] = []
    for candidate in payload.get("candidates", []) or []:
        content = candidate.get("content") or {}
        for part in content.get("parts", []) or []:
            text = str(part.get("text", "")).strip()
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def _build_ollama_client() -> Any:
    return _RequestsOllamaClient()


def _build_gemini_client() -> Any:
    return _RequestsGeminiClient()


@lru_cache(maxsize=3)
def get_llm(provider: str | None = None) -> Any:
    selected_provider = resolve_llm_provider(provider)
    if selected_provider == "gemini":
        return _build_gemini_client()
    return _build_ollama_client()


def invoke_llm(prompt: str, provider: str | None = None) -> str:
    selected_provider = resolve_llm_provider(provider)

    try:
        result = get_llm(selected_provider).invoke(prompt)
    except LLMInvocationError:
        logger.exception(
            "Không thể gọi provider=%s model=%s (configured provider=%s)",
            selected_provider,
            GEMINI_MODEL if selected_provider == "gemini" else OLLAMA_MODEL,
            LLM_PROVIDER,
        )
        raise
    except Exception:
        logger.exception(
            "Không thể gọi provider=%s model=%s (configured provider=%s)",
            selected_provider,
            GEMINI_MODEL if selected_provider == "gemini" else OLLAMA_MODEL,
            LLM_PROVIDER,
        )
        raise

    if isinstance(result, str):
        return result.strip()

    content = getattr(result, "content", "")
    return str(content).strip()
