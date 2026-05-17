from __future__ import annotations

import hmac
from urllib.parse import quote_plus

from fastapi import Request
from fastapi.responses import RedirectResponse

from config.settings import settings


ADMIN_SESSION_KEY = "admin_authenticated"
ADMIN_USER_KEY = "admin_username"


def is_admin_authenticated(request: Request) -> bool:
    return bool(request.session.get(ADMIN_SESSION_KEY))


def authenticate_admin(username: str, password: str) -> bool:
    return hmac.compare_digest(username.strip(), settings.ADMIN_USERNAME) and hmac.compare_digest(
        password,
        settings.ADMIN_PASSWORD,
    )


def login_admin(request: Request, username: str) -> None:
    request.session[ADMIN_SESSION_KEY] = True
    request.session[ADMIN_USER_KEY] = username.strip()


def logout_admin(request: Request) -> None:
    request.session.pop(ADMIN_SESSION_KEY, None)
    request.session.pop(ADMIN_USER_KEY, None)


def admin_login_redirect(request: Request) -> RedirectResponse:
    next_path = str(request.url.path or "/")
    if request.url.query:
        next_path = f"{next_path}?{request.url.query}"
    return RedirectResponse(f"/admin/login?next={quote_plus(next_path)}", status_code=303)
