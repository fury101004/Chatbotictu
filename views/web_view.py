from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse


PAGE_TEMPLATES = {
    "home": "pages/index.html",
    "chat": "pages/chat.html",
    "data_loader": "pages/data_loader.html",
    "vector_manager": "pages/vector_manager_v2.html",
    "knowledge_base": "pages/knowledge_base.html",
    "config": "pages/config.html",
    "history": "pages/history.html",
    "cskh": "pages/cskh.html",
    "cskh_panel": "pages/cskh_panel.html",
}


def _render_template(request: Request, template_name: str, context: dict):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, template_name, context)



def render_home(request: Request):
    return _render_template(request, PAGE_TEMPLATES["home"], {})



def render_chat_page(request: Request, *, chat_model_options: list[dict[str, str]] | None = None):
    return _render_template(
        request,
        PAGE_TEMPLATES["chat"],
        {
            "chat_model_options": chat_model_options or [],
        },
    )



def current_prompt_response(prompt: str):
    return PlainTextResponse(prompt)



def render_data_loader_page(
    request: Request,
    *,
    chunk_size: int,
    chunk_overlap: int,
    tool_options: list[dict[str, str]],
    default_tool: str,
    csrf_token: str,
):
    return _render_template(
        request,
        PAGE_TEMPLATES["data_loader"],
        {
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "tool_options": tool_options,
            "default_tool": default_tool,
            "csrf_token": csrf_token,
        },
    )



def json_upload_result(result: dict):
    return JSONResponse(result)



def unauthorized_response(message: str = "Unauthorized"):
    return HTMLResponse(message, status_code=403)



def redirect_vector_manager():
    return RedirectResponse("/vector-manager", status_code=303)



def render_vector_manager_page(request: Request, *, payload: dict, csrf_token: str):
    return _render_template(
        request,
        PAGE_TEMPLATES["vector_manager"],
        {
            **payload,
            "csrf_token": csrf_token,
        },
    )



def render_knowledge_base_page(request: Request, *, payload: dict):
    return _render_template(request, PAGE_TEMPLATES["knowledge_base"], payload)


def render_config_page(
    request: Request,
    *,
    chunk_size: int,
    chunk_overlap: int,
    bot_rules: str,
    model_name: str,
    csrf_token: str,
    model_names: list[str] | None = None,
    model_rotation: str = "round_robin",
):
    return _render_template(
        request,
        PAGE_TEMPLATES["config"],
        {
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "bot_rules": bot_rules,
            "model_name": model_name,
            "csrf_token": csrf_token,
            "model_names": model_names or [],
            "model_rotation": model_rotation,
        },
    )



def render_history_page(request: Request, *, payload: dict):
    return _render_template(request, PAGE_TEMPLATES["history"], payload)
