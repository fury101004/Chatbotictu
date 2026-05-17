from __future__ import annotations

from urllib.parse import quote_plus

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse

from config.limiter import limiter
from config.rag_tools import DEFAULT_RAG_TOOL, get_upload_tool_options
from config.settings import settings
from config.system_prompt import get_system_prompt
from shared.web_session import ensure_csrf_token, resolve_chat_session_id, rotate_csrf_token, validate_csrf_token
from services.chat.chat_service import process_chat_message
from services.admin_auth_service import (
    admin_login_redirect,
    authenticate_admin,
    is_admin_authenticated,
    login_admin,
    logout_admin,
)
from services.config_service import get_config_page_payload, update_runtime_config
from services.content.document_service import (
    delete_uploaded_document,
    get_history_page_data,
    get_vector_manager_payload,
    import_seed_corpus,
    reingest_uploaded_documents,
    reset_document_store,
    upload_markdown_files,
)
from services.content.knowledge_base_service import approve_chat_entry, get_knowledge_base_payload, reject_chat_entry
from services.llm.llm_service import get_chat_model_options
from services.vector.vector_admin_service import delete_chunk_by_id
from views.web_view import current_prompt_response, json_upload_result, render_page, redirect_vector_manager, unauthorized_response

router = APIRouter()

HOME_TEMPLATE = "pages/index.html"
CHAT_TEMPLATE = "pages/chat.html"
DATA_LOADER_TEMPLATE = "pages/data_loader.html"
VECTOR_MANAGER_TEMPLATE = "pages/vector_manager_v2.html"
KNOWLEDGE_BASE_TEMPLATE = "pages/knowledge_base.html"
CONFIG_TEMPLATE = "pages/config.html"
HISTORY_TEMPLATE = "pages/history.html"
ADMIN_LOGIN_TEMPLATE = "pages/admin_login.html"


def _admin_required(request: Request):
    if is_admin_authenticated(request):
        return None
    return admin_login_redirect(request)


def _admin_required_json(request: Request):
    if is_admin_authenticated(request):
        return None
    return JSONResponse({"status": "error", "msg": "Admin authentication required"}, status_code=401)


def _safe_next_path(next_path: str) -> str:
    candidate = str(next_path or "").strip()
    if not candidate.startswith("/") or candidate.startswith("//"):
        return "/"
    if candidate.startswith("/admin/login"):
        return "/"
    return candidate


@router.get("/")
async def home(request: Request):
    return render_page(request, HOME_TEMPLATE)


@router.get("/admin/login")
async def admin_login_page(request: Request, next: str = "/"):
    return render_page(
        request,
        ADMIN_LOGIN_TEMPLATE,
        context={
            "csrf_token": ensure_csrf_token(request),
            "next_path": _safe_next_path(next),
            "error": "",
        },
    )


@router.post("/admin/login")
@limiter.limit(settings.API_RATE_ADMIN)
async def admin_login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next_path: str = Form("/"),
    csrf_token: str = Form(...),
):
    next_target = _safe_next_path(next_path)
    if not validate_csrf_token(request, csrf_token):
        return render_page(
            request,
            ADMIN_LOGIN_TEMPLATE,
            context={
                "csrf_token": ensure_csrf_token(request),
                "next_path": next_target,
                "error": "CSRF không hợp lệ.",
            },
        )

    if not authenticate_admin(username, password):
        rotate_csrf_token(request)
        return render_page(
            request,
            ADMIN_LOGIN_TEMPLATE,
            context={
                "csrf_token": ensure_csrf_token(request),
                "next_path": next_target,
                "error": "Sai tài khoản hoặc mật khẩu.",
            },
        )

    login_admin(request, username)
    rotate_csrf_token(request)
    return RedirectResponse(next_target, status_code=303)


@router.get("/admin/logout")
async def admin_logout(request: Request):
    logout_admin(request)
    rotate_csrf_token(request)
    return RedirectResponse("/chat", status_code=303)


@router.get("/chat")
async def chat_page(request: Request):
    resolve_chat_session_id(request, "default")
    return render_page(
        request,
        CHAT_TEMPLATE,
        context={"chat_model_options": get_chat_model_options()},
    )


@router.post("/chat")
@limiter.limit(settings.API_RATE_CHAT)
async def chat_web(
    request: Request,
    message: str = Form(...),
    session_id: str = Form("default"),
    llm_model: str = Form("auto"),
):
    current_session_id = resolve_chat_session_id(request, session_id)

    result = await process_chat_message(message, current_session_id, llm_model=llm_model)
    result["session_id"] = current_session_id
    return result


@router.post("/delete-file")
async def delete_file(request: Request, filename: str = Form(...), csrf_token: str = Form(...)):
    if not validate_csrf_token(request, csrf_token):
        return unauthorized_response("CSRF Invalid!")
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response

    delete_uploaded_document(filename)
    rotate_csrf_token(request)
    return redirect_vector_manager()


@router.get("/get-current-prompt")
async def get_current_prompt_view(request: Request):
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response
    return current_prompt_response(get_system_prompt())


@router.get("/data-loader")
async def data_loader_page(request: Request):
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response
    return render_page(
        request,
        DATA_LOADER_TEMPLATE,
        context={
            "chunk_size": settings.CHUNK_SIZE,
            "chunk_overlap": settings.CHUNK_OVERLAP,
            "tool_options": get_upload_tool_options(),
            "default_tool": DEFAULT_RAG_TOOL,
            "csrf_token": ensure_csrf_token(request),
        },
    )


@router.post("/upload")
@limiter.limit(settings.API_RATE_UPLOAD)
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    tool_name: str = Form(DEFAULT_RAG_TOOL),
    client_start_time: float = Form(None),
    client_total_size: int = Form(None),
    csrf_token: str = Form(...),
):
    if not validate_csrf_token(request, csrf_token):
        return JSONResponse({"status": "error", "msg": "CSRF Invalid!"}, status_code=403)
    admin_response = _admin_required_json(request)
    if admin_response is not None:
        return admin_response

    result = await upload_markdown_files(
        files=files,
        tool_name=tool_name,
        client_start_time=client_start_time,
        client_total_size=client_total_size,
    )
    return json_upload_result(result)


@router.post("/import-qa-corpus")
@limiter.limit(settings.API_RATE_ADMIN)
async def import_qa_corpus(request: Request, csrf_token: str = Form(...), reset_first: bool = Form(False)):
    if not validate_csrf_token(request, csrf_token):
        return JSONResponse({"status": "error", "msg": "CSRF Invalid!"}, status_code=403)
    admin_response = _admin_required_json(request)
    if admin_response is not None:
        return admin_response

    result = import_seed_corpus(reset_first=reset_first)
    next_csrf_token = rotate_csrf_token(request)

    status_code = 200 if result.get("status") in {"success", "partial"} else 500
    return JSONResponse(
        {
            **result,
            "csrf_token": next_csrf_token,
        },
        status_code=status_code,
    )


@router.post("/reset-vectorstore")
@limiter.limit(settings.API_RATE_ADMIN)
async def reset_vs(request: Request, csrf_token: str = Form(...)):
    if not validate_csrf_token(request, csrf_token):
        return unauthorized_response()
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response

    reset_document_store()
    rotate_csrf_token(request)
    return redirect_vector_manager()


@router.get("/vector-manager")
async def vector_manager(request: Request, limit_per_file: int = 50):
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response
    payload = get_vector_manager_payload(limit_per_file)
    return render_page(
        request,
        VECTOR_MANAGER_TEMPLATE,
        context={
            **payload,
            "csrf_token": ensure_csrf_token(request),
        },
    )


@router.get("/knowledge-base")
async def knowledge_base_page(
    request: Request,
    q: str = "",
    limit: int = 18,
    status: str = "",
    message: str = "",
):
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response
    payload = get_knowledge_base_payload(query=q, limit=limit)
    payload["csrf_token"] = ensure_csrf_token(request)
    payload["flash_status"] = status
    payload["flash_message"] = message
    return render_page(request, KNOWLEDGE_BASE_TEMPLATE, context=payload)


@router.post("/knowledge-base/approve-chat")
@limiter.limit(settings.API_RATE_ADMIN)
async def approve_chat_to_knowledge_base(
    request: Request,
    entry_id: str = Form(...),
    tool_name: str = Form(DEFAULT_RAG_TOOL),
    return_q: str = Form(""),
    csrf_token: str = Form(...),
):
    if not validate_csrf_token(request, csrf_token):
        return unauthorized_response("CSRF Invalid!")
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response

    try:
        result = approve_chat_entry(entry_id=entry_id, tool_name=tool_name)
        message = result["message"]
        if result.get("warning"):
            message = f"{message} {result['warning']}"
        redirect_url = (
            f"/knowledge-base?q={quote_plus(return_q)}"
            f"&status=success&message={quote_plus(message)}"
        )
    except Exception as exc:
        redirect_url = (
            f"/knowledge-base?q={quote_plus(return_q)}"
            f"&status=error&message={quote_plus(str(exc))}"
        )

    rotate_csrf_token(request)
    return RedirectResponse(redirect_url, status_code=303)


@router.post("/knowledge-base/reject-chat")
@limiter.limit(settings.API_RATE_ADMIN)
async def reject_chat_from_knowledge_base(
    request: Request,
    entry_id: str = Form(...),
    reason: str = Form(""),
    return_q: str = Form(""),
    csrf_token: str = Form(...),
):
    if not validate_csrf_token(request, csrf_token):
        return unauthorized_response("CSRF Invalid!")
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response

    try:
        result = reject_chat_entry(entry_id=entry_id, reason=reason)
        redirect_url = (
            f"/knowledge-base?q={quote_plus(return_q)}"
            f"&status=success&message={quote_plus(result['message'])}"
        )
    except Exception as exc:
        redirect_url = (
            f"/knowledge-base?q={quote_plus(return_q)}"
            f"&status=error&message={quote_plus(str(exc))}"
        )

    rotate_csrf_token(request)
    return RedirectResponse(redirect_url, status_code=303)


@router.get("/config")
async def config_page(request: Request):
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response
    payload = get_config_page_payload()
    return render_page(
        request,
        CONFIG_TEMPLATE,
        context={
            **payload,
            "csrf_token": ensure_csrf_token(request),
        },
    )


@router.post("/update-config")
@limiter.limit(settings.API_RATE_ADMIN)
async def update_config(
    request: Request,
    chunk_size: int = Form(...),
    chunk_overlap: int = Form(...),
    bot_rules: str = Form(...),
    reingest: bool = Form(False),
    csrf_token: str = Form(...),
):
    if not validate_csrf_token(request, csrf_token):
        return JSONResponse({"msg": "CSRF Invalid!"}, status_code=403)
    admin_response = _admin_required_json(request)
    if admin_response is not None:
        return admin_response

    result = update_runtime_config(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        bot_rules=bot_rules,
        reingest=reingest,
        reingest_callback=reingest_uploaded_documents,
    )
    return JSONResponse(result)


@router.post("/delete-chunk")
@limiter.limit(settings.API_RATE_ADMIN)
async def delete_chunk(request: Request, chunk_id: str = Form(...), csrf_token: str = Form(...)):
    if not validate_csrf_token(request, csrf_token):
        return JSONResponse({"status": "error", "error": "CSRF Invalid!"}, status_code=403)
    admin_response = _admin_required_json(request)
    if admin_response is not None:
        return admin_response

    try:
        delete_chunk_by_id(chunk_id)
        return {"status": "ok"}
    except Exception:
        return {"status": "error"}


@router.get("/history")
async def history_page(request: Request, page: int = 1):
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response
    payload = get_history_page_data(page=page, per_page=50)
    payload["csrf_token"] = ensure_csrf_token(request)
    return render_page(request, HISTORY_TEMPLATE, context=payload)


def register_web_routes(app) -> None:
    app.include_router(router)

