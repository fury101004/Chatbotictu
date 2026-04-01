"""Chat orchestration service."""

from __future__ import annotations

from typing import Dict

from app.services.history_service import list_history_for_rag, save_exchange
from app.services.rag_service import rag_chat


def process_chat_message(user_id: str, message: str) -> Dict[str, object]:
    cleaned_message = " ".join((message or "").split())
    if not cleaned_message:
        raise ValueError("Tin nhan khong duoc de trong.")

    history = list_history_for_rag(user_id)
    result = rag_chat(cleaned_message, history)
    save_exchange(user_id, cleaned_message, result["answer"])
    return result
