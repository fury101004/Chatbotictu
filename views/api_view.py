from __future__ import annotations

from datetime import datetime
from typing import Optional

from config.settings import settings
from models.chat import ChatResponse
from services.llm_service import PRIMARY_MODEL_NAME, get_model
from services.vector_store_service import embedding_backend_ready


def build_token_response(token: str) -> dict:
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 86400,
    }


def build_chat_response(result: dict, session_id: str) -> ChatResponse:
    return ChatResponse(
        **result,
        timestamp=datetime.now().isoformat(),
        session_id=session_id,
    )


def build_upload_response(result: dict, session_id: Optional[str]) -> dict:
    return {
        "status": result.get("status", "success"),
        **result,
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
    }


def build_knowledge_base_response(payload: dict) -> dict:
    return {
        **payload,
        "timestamp": datetime.now().isoformat(),
    }


def build_health_response() -> dict:
    configured_model = get_model()
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "model": PRIMARY_MODEL_NAME,
        "llm_configured": configured_model is not None,
        "embedding_backend_ready": embedding_backend_ready(),
        "timestamp": datetime.now().isoformat(),
    }
