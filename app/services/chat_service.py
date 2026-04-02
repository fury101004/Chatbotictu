"""Chat orchestration service."""

from __future__ import annotations

import logging
from typing import Dict

from app.services.history_service import list_history_for_rag, save_exchange


logger = logging.getLogger(__name__)


def process_chat_message(user_id: str, message: str) -> Dict[str, object]:
    cleaned_message = " ".join((message or "").split())
    if not cleaned_message:
        raise ValueError("Tin nhắn không được để trống.")

    from app.services.rag_service import rag_chat

    history = list_history_for_rag(user_id)
    result = rag_chat(cleaned_message, history)

    try:
        save_exchange(user_id, cleaned_message, result["answer"])
    except Exception as exc:  # pragma: no cover - defensive persistence fallback
        logger.warning("Không thể lưu lịch sử chat cho user_id=%s: %s", user_id, exc)

    return result
