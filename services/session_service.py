from __future__ import annotations

from typing import Any


_SESSIONS: dict[str, dict[str, Any]] = {}
_LAST_CALLS: dict[str, float] = {}


def get_session_state(session_id: str) -> dict[str, Any]:
    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = {"lang": "vi", "history": []}
    return _SESSIONS[session_id]


def get_session_language(session_id: str) -> str:
    return str(get_session_state(session_id).get("lang", "vi") or "vi")


def set_session_language(session_id: str, language: str) -> None:
    get_session_state(session_id)["lang"] = str(language or "vi")


def append_session_history(session_id: str, items: list[dict[str, str]], *, max_items: int = 30) -> None:
    session = get_session_state(session_id)
    history = list(session.get("history", []))
    history.extend(items)
    session["history"] = history[-max_items:]


def get_session_history(session_id: str) -> list[dict[str, str]]:
    return list(get_session_state(session_id).get("history", []))


def get_last_call_at(session_id: str) -> float | None:
    return _LAST_CALLS.get(session_id)


def mark_call(session_id: str, timestamp: float) -> None:
    _LAST_CALLS[session_id] = float(timestamp)


def clear_session_state(session_id: str) -> None:
    _SESSIONS.pop(session_id, None)
    _LAST_CALLS.pop(session_id, None)
