from __future__ import annotations

import secrets

from fastapi import Request


def ensure_session_value(request: Request, key: str, *, length: int = 16) -> str:
    value = str(request.session.get(key) or "").strip()
    if value:
        return value

    value = secrets.token_hex(length)
    request.session[key] = value
    return value


def ensure_csrf_token(request: Request) -> str:
    return ensure_session_value(request, "csrf_token")


def rotate_csrf_token(request: Request) -> str:
    token = secrets.token_hex(16)
    request.session["csrf_token"] = token
    return token


def validate_csrf_token(request: Request, token: str) -> bool:
    return str(request.session.get("csrf_token") or "") == str(token or "")


def resolve_chat_session_id(request: Request, session_id: str) -> str:
    candidate = str(session_id or "").strip()
    if candidate and candidate != "default":
        return candidate
    return ensure_session_value(request, "chat_session_id")
