from __future__ import annotations

import time
from typing import Any, Callable

from models.chat import ChatGraphState


StepHandler = Callable[[ChatGraphState], ChatGraphState]


async def process_chat_message(
    *,
    message: str,
    session_id: str,
    llm_model: str,
    steps: tuple[StepHandler, ...],
) -> dict[str, Any]:
    started_at = time.perf_counter()
    state: ChatGraphState = {
        "message": message,
        "session_id": session_id,
        "selected_llm_model": llm_model,
    }

    for step in steps:
        state = step(state)
        if state.get("stop_graph"):
            break

    response_time_ms = int((time.perf_counter() - started_at) * 1000)
    state["response_time_ms"] = response_time_ms
    return build_chat_response_payload(state, response_time_ms=response_time_ms)


def build_chat_response_payload(state: ChatGraphState, *, response_time_ms: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "response": state.get("response", ""),
        "language": state.get("language"),
        "intent": state.get("intent"),
        "needs_clarification": state.get("needs_clarification"),
        "response_time_ms": response_time_ms,
    }

    for key in (
        "sources",
        "mode",
        "chunks_used",
        "rag_tool",
        "rag_route",
        "llm_model",
        "web_kb_status",
        "auto_approved_kb",
        "qa_review_status",
        "qa_review_entry_id",
    ):
        if state.get(key) is not None:
            result[key] = state.get(key)
    return result
