from __future__ import annotations

from datetime import datetime
from typing import Optional

from models.chat import ChatResponse



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
        "status": "success",
        **result,
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
    }



def build_health_response() -> dict:
    return {
        "status": "healthy",
        "model": "gemini-2.5-flash",
        "timestamp": datetime.now().isoformat(),
    }




