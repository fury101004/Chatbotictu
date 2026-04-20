from __future__ import annotations

from datetime import datetime
from typing import Optional

from models.chat import ChatResponse
from services.llm_service import PRIMARY_MODEL_NAME



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
    return {
        "status": "healthy",
        "model": PRIMARY_MODEL_NAME,
        "timestamp": datetime.now().isoformat(),
    }


