from __future__ import annotations

import hmac
from urllib.parse import quote_plus

from fastapi import Request
from fastapi.responses import RedirectResponse

from config.settings import settings


ADMIN_SESSION_KEY = "admin_authenticated"
ADMIN_USER_KEY = "admin_username"
ADMIN_ROLE_KEY = "admin_role"
AUTH_SESSION_KEY = "web_authenticated"
AUTH_USER_KEY = "web_username"
AUTH_ROLE_KEY = "web_role"

ADMIN_ROLE = "admin"
USER_ROLES = {"user", "student"}


def normalize_role(role: str | None) -> str:
    normalized = str(role or "").strip().lower()
    if normalized == settings.ADMIN_ROLE.strip().lower() or normalized == ADMIN_ROLE:
        return ADMIN_ROLE
    if normalized in USER_ROLES:
        return normalized
    return "guest"


def get_current_role(request: Request) -> str:
    authenticated = bool(request.session.get(AUTH_SESSION_KEY) or request.session.get(ADMIN_SESSION_KEY))
    if not authenticated:
        return "guest"
    if request.session.get(ADMIN_SESSION_KEY) and not request.session.get(AUTH_ROLE_KEY):
        return ADMIN_ROLE
    return normalize_role(request.session.get(AUTH_ROLE_KEY) or request.session.get(ADMIN_ROLE_KEY))


def is_web_authenticated(request: Request) -> bool:
    return get_current_role(request) in {ADMIN_ROLE, *USER_ROLES}


def is_admin_authenticated(request: Request) -> bool:
    return get_current_role(request) == ADMIN_ROLE


def authenticate_admin(username: str, password: str) -> bool:
    return hmac.compare_digest(username.strip(), settings.ADMIN_USERNAME) and hmac.compare_digest(
        password,
        settings.ADMIN_PASSWORD,
    )


def authenticate_user(username: str, password: str) -> bool:
    return hmac.compare_digest(username.strip(), settings.USER_USERNAME) and hmac.compare_digest(
        password,
        settings.USER_PASSWORD,
    )


def authenticate_web_user(username: str, password: str) -> str | None:
    if authenticate_admin(username, password):
        return ADMIN_ROLE
    if authenticate_user(username, password):
        return normalize_role(settings.USER_ROLE)
    return None


def login_with_role(request: Request, username: str, role: str) -> None:
    normalized_role = normalize_role(role)
    request.session[AUTH_SESSION_KEY] = True
    request.session[AUTH_USER_KEY] = username.strip()
    request.session[AUTH_ROLE_KEY] = normalized_role

    if normalized_role == ADMIN_ROLE:
        request.session[ADMIN_SESSION_KEY] = True
        request.session[ADMIN_USER_KEY] = username.strip()
        request.session[ADMIN_ROLE_KEY] = settings.ADMIN_ROLE
    else:
        request.session.pop(ADMIN_SESSION_KEY, None)
        request.session.pop(ADMIN_USER_KEY, None)
        request.session.pop(ADMIN_ROLE_KEY, None)


def login_admin(request: Request, username: str) -> None:
    login_with_role(request, username, ADMIN_ROLE)


def logout_admin(request: Request) -> None:
    logout_web_user(request)


def logout_web_user(request: Request) -> None:
    request.session.pop(AUTH_SESSION_KEY, None)
    request.session.pop(AUTH_USER_KEY, None)
    request.session.pop(AUTH_ROLE_KEY, None)
    request.session.pop(ADMIN_SESSION_KEY, None)
    request.session.pop(ADMIN_USER_KEY, None)
    request.session.pop(ADMIN_ROLE_KEY, None)


def default_route_for_role(role: str) -> str:
    return "/" if normalize_role(role) == ADMIN_ROLE else "/chat"


def admin_login_redirect(request: Request) -> RedirectResponse:
    next_path = str(request.url.path or "/")
    if request.url.query:
        next_path = f"{next_path}?{request.url.query}"
    return RedirectResponse(f"/login?next={quote_plus(next_path)}", status_code=303)


def login_redirect(request: Request) -> RedirectResponse:
    return admin_login_redirect(request)
