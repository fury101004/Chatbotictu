from __future__ import annotations

import uuid

from fastapi import Request


def get_or_create_user_id(request: Request) -> str:
    user_id = request.session.get("user_id")
    if not user_id:
        user_id = str(uuid.uuid4())
        request.session["user_id"] = user_id
    return user_id
