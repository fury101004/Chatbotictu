from __future__ import annotations

from typing import Any, Dict

from fastapi import Request

from app.core.config import (
    ACTIVE_LLM_MODEL,
    ACTIVE_LLM_PROVIDER,
    APP_NAME,
    GEMINI_API_KEY,
    MAX_UPLOAD_SIZE_MB,
    UPLOADS_DIR_NAME,
    VECTOR_DB_DIR,
)


def page_context(request: Request, *, active: str, title: str, **extra: Any) -> Dict[str, Any]:
    context: Dict[str, Any] = {
        "request": request,
        "active": active,
        "title": title,
        "app_name": APP_NAME,
        "current_provider": ACTIVE_LLM_PROVIDER,
        "provider_model": ACTIVE_LLM_MODEL,
        "gemini_ready": bool(GEMINI_API_KEY),
        "max_upload_size_mb": MAX_UPLOAD_SIZE_MB,
        "uploads_dir_name": UPLOADS_DIR_NAME,
        "vector_root": str(VECTOR_DB_DIR),
    }
    context.update(extra)
    return context
