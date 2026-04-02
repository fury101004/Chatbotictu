from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.api.deps import get_or_create_user_id
from app.core.config import APP_DEBUG
from app.services.llm_service import sanitize_debug_detail


router = APIRouter(tags=["chat"])


class ChatPayload(BaseModel):
    message: str


def _runtime_error_detail(message: str, exc: Exception) -> str:
    detail = message
    if APP_DEBUG:
        debug_detail = sanitize_debug_detail(str(exc))
        if debug_detail:
            detail = f"{detail} Chi tiết dev: {debug_detail}"
    return detail


@router.post("/api/chat")
def chat_api(payload: ChatPayload, request: Request):
    message = str(payload.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Tin nhắn không được để trống.")

    try:
        from app.services.chat_service import process_chat_message
    except (ModuleNotFoundError, ImportError) as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Chat service chưa sẵn sàng vì thiếu dependency: "
                f"{getattr(exc, 'name', None) or exc.__class__.__name__}."
            ),
        ) from exc

    user_id = get_or_create_user_id(request)

    try:
        result = process_chat_message(user_id, message)
    except (ModuleNotFoundError, ImportError) as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Chat service chưa sẵn sàng vì thiếu dependency: "
                f"{getattr(exc, 'name', None) or exc.__class__.__name__}."
            ),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=_runtime_error_detail("Không thể xử lý yêu cầu lúc này.", exc),
        ) from exc

    return {
        "reply": result["answer"],
        "route": result["route"],
        "agent": result.get("agent", result["route"]),
        "agent_label": result.get("agent_label", result["route"]),
        "sources": result.get("sources", []),
        "provider": result.get("provider"),
    }
