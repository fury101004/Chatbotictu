from __future__ import annotations

from typing import Any, Mapping

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse

from services.admin_auth_service import is_admin_authenticated


def render_page(
    request: Request,
    template_name: str,
    *,
    context: Mapping[str, Any] | None = None,
):
    templates = request.app.state.templates
    page_context = dict(context or {})
    page_context.setdefault("admin_authenticated", is_admin_authenticated(request))
    return templates.TemplateResponse(request, template_name, page_context)


def current_prompt_response(prompt: str):
    return PlainTextResponse(prompt)


def json_upload_result(result: dict):
    return JSONResponse(result)


def unauthorized_response(message: str = "Unauthorized"):
    return HTMLResponse(message, status_code=403)


def redirect_vector_manager():
    return RedirectResponse("/vector-manager", status_code=303)
