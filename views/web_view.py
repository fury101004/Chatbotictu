from __future__ import annotations

from typing import Any, Mapping

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse

from services.admin_auth_service import get_current_role, is_admin_authenticated, is_web_authenticated
from services.navigation_service import NAV_ICONS, get_logout_label, get_menu_items


def render_page(
    request: Request,
    template_name: str,
    *,
    context: Mapping[str, Any] | None = None,
):
    templates = request.app.state.templates
    page_context = dict(context or {})
    current_role = get_current_role(request)
    authenticated = is_web_authenticated(request)
    page_context.setdefault("current_role", current_role)
    page_context.setdefault("is_authenticated", authenticated)
    page_context.setdefault("admin_authenticated", is_admin_authenticated(request))
    page_context.setdefault("nav_menu_items", get_menu_items(current_role) if authenticated else [])
    page_context.setdefault("nav_icons", NAV_ICONS)
    page_context.setdefault("logout_path", "/logout")
    page_context.setdefault("logout_label", get_logout_label(current_role))
    return templates.TemplateResponse(request, template_name, page_context)


def current_prompt_response(prompt: str):
    return PlainTextResponse(prompt)


def json_upload_result(result: dict):
    return JSONResponse(result)


def unauthorized_response(message: str = "Unauthorized"):
    return HTMLResponse(message, status_code=403)


def redirect_vector_manager():
    return RedirectResponse("/vector-manager", status_code=303)
