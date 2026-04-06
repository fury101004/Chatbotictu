from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse


PAGE_TEMPLATES = {
    "home": "pages/index.html",
    "chat": "pages/chat.html",
    "data_loader": "pages/data_loader.html",
    "vector_manager": "pages/vector_manager_v2.html",
    "config": "pages/config.html",
    "history": "pages/history.html",
    "cskh": "pages/cskh.html",
    "cskh_panel": "pages/cskh_panel.html",
}


def _render_template(request: Request, template_name: str, context: dict):
    templates = request.app.state.templates
    return templates.TemplateResponse(template_name, {"request": request, **context})



def render_home(request: Request):
    return _render_template(request, PAGE_TEMPLATES["home"], {})



def render_chat_page(request: Request):
    return _render_template(request, PAGE_TEMPLATES["chat"], {})



def current_prompt_response(prompt: str):
    return PlainTextResponse(prompt)



def render_data_loader_page(request: Request, *, chunk_size: int, chunk_overlap: int):
    return _render_template(
        request,
        PAGE_TEMPLATES["data_loader"],
        {
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
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



def render_config_page(
    request: Request,
    *,
    chunk_size: int,
    chunk_overlap: int,
    bot_rules: str,
    model_name: str,
):
    return _render_template(
        request,
        PAGE_TEMPLATES["config"],
        {
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "bot_rules": bot_rules,
            "model_name": model_name,
        },
    )



def render_history_page(request: Request, *, payload: dict):
    return _render_template(request, PAGE_TEMPLATES["history"], payload)
