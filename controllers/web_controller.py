from __future__ import annotations

import html
from urllib.parse import quote_plus

from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse

from config.limiter import limiter
from config.rag_tools import DEFAULT_RAG_TOOL, get_upload_tool_options
from config.settings import settings
from config.system_prompt import get_system_prompt
from models.chat import MAX_CHAT_MESSAGE_CHARS, MAX_CHAT_MODEL_CHARS, MAX_CHAT_SESSION_ID_CHARS
from shared.web_session import ensure_csrf_token, resolve_chat_session_id, rotate_csrf_token, validate_csrf_token
from services.chat.chat_service import process_chat_message
from services.admin_auth_service import (
    admin_login_redirect,
    authenticate_web_user,
    create_managed_user,
    default_route_for_role,
    delete_managed_user,
    get_current_role,
    get_current_username,
    get_user_management_payload,
    is_admin_authenticated,
    is_web_authenticated,
    login_with_role,
    logout_web_user,
    register_web_user,
    update_managed_user,
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
from services.ingestion_queue import get_ingestion_queue
from services.llm.llm_service import get_chat_model_options
from services.rag.source_display_service import format_source_label
from services.user_feedback_service import save_user_feedback
from services.vector.vector_admin_service import delete_chunk_by_id
from repositories.vector_repository import fetch_documents_by_source
from views.web_view import current_prompt_response, render_page, redirect_vector_manager, unauthorized_response

router = APIRouter()

HOME_TEMPLATE = "pages/index.html"
USER_HOME_TEMPLATE = "pages/user_home.html"
CHAT_TEMPLATE = "pages/chat.html"
DATA_LOADER_TEMPLATE = "pages/data_loader.html"
VECTOR_MANAGER_TEMPLATE = "pages/vector_manager_v2.html"
KNOWLEDGE_BASE_TEMPLATE = "pages/knowledge_base.html"
CONFIG_TEMPLATE = "pages/config.html"
HISTORY_TEMPLATE = "pages/history.html"
ADMIN_LOGIN_TEMPLATE = "pages/admin_login.html"
REGISTER_TEMPLATE = "pages/register.html"
USER_MANAGEMENT_TEMPLATE = "pages/user_management.html"
EVALUATION_DASHBOARD_HTML = settings.PROJECT_ROOT / "views" / "frontend" / "evaluation_dashboard.html"


def _login_required(request: Request):
    if is_web_authenticated(request):
        return None
    return admin_login_redirect(request)


def _admin_required(request: Request):
    login_response = _login_required(request)
    if login_response is not None:
        return login_response
    if is_admin_authenticated(request):
        return None
    return RedirectResponse("/chat", status_code=303)


def _evaluation_dashboard_required(request: Request):
    login_response = _login_required(request)
    if login_response is not None:
        return login_response
    if not is_admin_authenticated(request):
        return HTMLResponse("Admin role required", status_code=403)
    return None


def _admin_required_json(request: Request):
    if not is_web_authenticated(request):
        return JSONResponse({"status": "error", "msg": "Login required"}, status_code=401)
    if not is_admin_authenticated(request):
        return JSONResponse({"status": "error", "msg": "Admin role required"}, status_code=403)
    return None


def _safe_next_path(next_path: str) -> str:
    candidate = str(next_path or "").strip()
    if not candidate.startswith("/") or candidate.startswith("//"):
        return "/"
    if candidate.startswith("/admin/login"):
        return "/login"
    if candidate.startswith("/login"):
        return "/login"
    if candidate.startswith("/register"):
        return "/login"
    return candidate


def _login_page_context(request: Request, next_path: str, error: str = "", success: str = "") -> dict:
    return {
        "csrf_token": ensure_csrf_token(request),
        "next_path": _safe_next_path(next_path),
        "error": error,
        "success": success,
    }


def _register_page_context(
    request: Request,
    error: str = "",
    form_values: dict[str, str] | None = None,
) -> dict:
    values = dict(form_values or {})
    return {
        "csrf_token": ensure_csrf_token(request),
        "error": error,
        "form_values": {
            "full_name": values.get("full_name", ""),
            "username": values.get("username", ""),
        },
    }


def _no_store_response(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def _user_management_context(
    request: Request,
    *,
    notice: str = "",
    error: str = "",
) -> dict:
    payload = get_user_management_payload()
    payload["csrf_token"] = ensure_csrf_token(request)
    payload["notice"] = notice
    payload["error"] = error
    return payload


def _render_user_management_page(
    request: Request,
    *,
    notice: str = "",
    error: str = "",
):
    return _no_store_response(
        render_page(
            request,
            USER_MANAGEMENT_TEMPLATE,
            context=_user_management_context(request, notice=notice, error=error),
        )
    )


def _chat_payload_error(message: str, session_id: str, llm_model: str):
    if not str(message or "").strip():
        return JSONResponse({"status": "error", "detail": "Message is required."}, status_code=422)
    if len(message) > MAX_CHAT_MESSAGE_CHARS:
        return JSONResponse(
            {
                "status": "error",
                "detail": f"Message is too long. Maximum is {MAX_CHAT_MESSAGE_CHARS} characters.",
            },
            status_code=400,
        )
    if len(str(session_id or "")) > MAX_CHAT_SESSION_ID_CHARS:
        return JSONResponse(
            {
                "status": "error",
                "detail": f"Session id is too long. Maximum is {MAX_CHAT_SESSION_ID_CHARS} characters.",
            },
            status_code=422,
        )
    if len(str(llm_model or "")) > MAX_CHAT_MODEL_CHARS:
        return JSONResponse(
            {
                "status": "error",
                "detail": f"LLM model value is too long. Maximum is {MAX_CHAT_MODEL_CHARS} characters.",
            },
            status_code=422,
        )
    return None


async def _submit_login(
    request: Request,
    username: str,
    password: str,
    next_path: str,
    csrf_token: str,
):
    next_target = _safe_next_path(next_path)
    if not validate_csrf_token(request, csrf_token):
        rotate_csrf_token(request)
        return _no_store_response(render_page(
            request,
            ADMIN_LOGIN_TEMPLATE,
            context=_login_page_context(request, next_target, "CSRF không hợp lệ."),
        ))

    role = authenticate_web_user(username, password)
    if role is None:
        rotate_csrf_token(request)
        return _no_store_response(render_page(
            request,
            ADMIN_LOGIN_TEMPLATE,
            context=_login_page_context(request, next_target, "Sai tài khoản hoặc mật khẩu."),
        ))

    login_with_role(request, username, role)
    rotate_csrf_token(request)
    return RedirectResponse(default_route_for_role(role), status_code=303)


@router.get("/")
async def home(request: Request):
    login_response = _login_required(request)
    if login_response is not None:
        return login_response
    if is_admin_authenticated(request):
        return render_page(request, HOME_TEMPLATE)
    return render_page(request, USER_HOME_TEMPLATE)


@router.get("/login")
async def login_page(request: Request, next: str = "/", registered: str = ""):
    if is_web_authenticated(request):
        return RedirectResponse(default_route_for_role(get_current_role(request)), status_code=303)
    success = "Đăng ký thành công. Vui lòng đăng nhập." if registered == "1" else ""
    return _no_store_response(render_page(
        request,
        ADMIN_LOGIN_TEMPLATE,
        context=_login_page_context(request, next, success=success),
    ))


@router.get("/admin/login")
async def admin_login_page(request: Request, next: str = "/"):
    if is_web_authenticated(request):
        return RedirectResponse(default_route_for_role(get_current_role(request)), status_code=303)
    return _no_store_response(render_page(
        request,
        ADMIN_LOGIN_TEMPLATE,
        context=_login_page_context(request, next),
    ))


@router.get("/register")
async def register_page(request: Request):
    if is_web_authenticated(request):
        return RedirectResponse(default_route_for_role(get_current_role(request)), status_code=303)
    return _no_store_response(render_page(
        request,
        REGISTER_TEMPLATE,
        context=_register_page_context(request),
    ))


@router.post("/login")
@limiter.limit(settings.API_RATE_ADMIN)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next_path: str = Form("/"),
    csrf_token: str = Form(...),
):
    return await _submit_login(request, username, password, next_path, csrf_token)


@router.post("/register")
@limiter.limit(settings.API_RATE_ADMIN)
async def register_submit(
    request: Request,
    full_name: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    confirm_password: str = Form(""),
    csrf_token: str = Form(""),
):
    if is_web_authenticated(request):
        return RedirectResponse(default_route_for_role(get_current_role(request)), status_code=303)

    form_values = {"full_name": full_name, "username": username}
    if not validate_csrf_token(request, csrf_token):
        rotate_csrf_token(request)
        return _no_store_response(render_page(
            request,
            REGISTER_TEMPLATE,
            context=_register_page_context(request, "CSRF không hợp lệ.", form_values),
        ))

    result = register_web_user(full_name, username, password, confirm_password)
    if not result.ok:
        rotate_csrf_token(request)
        return _no_store_response(render_page(
            request,
            REGISTER_TEMPLATE,
            context=_register_page_context(request, result.message, form_values),
        ))

    rotate_csrf_token(request)
    return RedirectResponse("/login?registered=1", status_code=303)


@router.get("/users")
async def user_management_page(request: Request, status: str = ""):
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response

    notices = {
        "created": "Đã tạo user mới.",
        "updated": "Đã cập nhật user.",
        "deleted": "Đã xóa user.",
    }
    return _render_user_management_page(request, notice=notices.get(status, ""))


@router.post("/users/create")
@limiter.limit(settings.API_RATE_ADMIN)
async def user_management_create(
    request: Request,
    full_name: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    role: str = Form("user"),
    csrf_token: str = Form(""),
):
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response
    if not validate_csrf_token(request, csrf_token):
        rotate_csrf_token(request)
        return _render_user_management_page(request, error="CSRF không hợp lệ.")

    result = create_managed_user(full_name, username, password, role)
    rotate_csrf_token(request)
    if not result.ok:
        return _render_user_management_page(request, error=result.message)
    return RedirectResponse("/users?status=created", status_code=303)


@router.post("/users/update")
@limiter.limit(settings.API_RATE_ADMIN)
async def user_management_update(
    request: Request,
    user_id: int = Form(...),
    full_name: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    role: str = Form("user"),
    csrf_token: str = Form(""),
):
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response
    if not validate_csrf_token(request, csrf_token):
        rotate_csrf_token(request)
        return _render_user_management_page(request, error="CSRF không hợp lệ.")

    result = update_managed_user(
        user_id,
        full_name=full_name,
        username=username,
        password=password,
        role=role,
    )
    rotate_csrf_token(request)
    if not result.ok:
        return _render_user_management_page(request, error=result.message)
    return RedirectResponse("/users?status=updated", status_code=303)


@router.post("/users/delete")
@limiter.limit(settings.API_RATE_ADMIN)
async def user_management_delete(
    request: Request,
    user_id: int = Form(...),
    csrf_token: str = Form(""),
):
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response
    if not validate_csrf_token(request, csrf_token):
        rotate_csrf_token(request)
        return _render_user_management_page(request, error="CSRF không hợp lệ.")

    result = delete_managed_user(user_id)
    rotate_csrf_token(request)
    if not result.ok:
        return _render_user_management_page(request, error=result.message)
    return RedirectResponse("/users?status=deleted", status_code=303)


@router.post("/admin/login")
@limiter.limit(settings.API_RATE_ADMIN)
async def admin_login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next_path: str = Form("/"),
    csrf_token: str = Form(...),
):
    return await _submit_login(request, username, password, next_path, csrf_token)


@router.get("/logout")
async def logout(request: Request):
    logout_web_user(request)
    rotate_csrf_token(request)
    return RedirectResponse("/login", status_code=303)


@router.get("/admin/logout")
async def admin_logout(request: Request):
    return await logout(request)


@router.get("/chat")
async def chat_page(request: Request):
    login_response = _login_required(request)
    if login_response is not None:
        return login_response
    resolve_chat_session_id(request, "default")
    return render_page(
        request,
        CHAT_TEMPLATE,
        context={
            "chat_model_options": get_chat_model_options(),
            "csrf_token": ensure_csrf_token(request),
            "max_chat_message_chars": MAX_CHAT_MESSAGE_CHARS,
        },
    )


@router.post("/chat")
@limiter.limit(settings.API_RATE_CHAT)
async def chat_web(
    request: Request,
    message: str = Form(...),
    session_id: str = Form("default"),
    llm_model: str = Form("auto"),
    csrf_token: str = Form(""),
):
    login_response = _login_required(request)
    if login_response is not None:
        return login_response
    if not validate_csrf_token(request, csrf_token):
        return JSONResponse({"status": "error", "detail": "CSRF Invalid!"}, status_code=403)
    payload_error = _chat_payload_error(message, session_id, llm_model)
    if payload_error is not None:
        return payload_error
    current_session_id = resolve_chat_session_id(request, session_id)

    current_role = get_current_role(request)
    current_username = get_current_username(request)
    result = await process_chat_message(
        message,
        current_session_id,
        llm_model=llm_model,
        owner_username=current_username,
        owner_role=current_role,
    )
    return {"response": str(result.get("response") or "")}


@router.post("/chat/feedback")
@limiter.limit(settings.API_RATE_CHAT)
async def chat_feedback(
    request: Request,
    session_id: str = Form(...),
    question: str = Form(...),
    answer: str = Form(...),
    thumbs_up: bool = Form(...),
    comment: str = Form(""),
    csrf_token: str = Form(""),
):
    if not is_web_authenticated(request):
        return JSONResponse({"status": "error", "detail": "Login required"}, status_code=401)
    if not validate_csrf_token(request, csrf_token):
        return JSONResponse({"status": "error", "detail": "CSRF Invalid!"}, status_code=403)

    cleaned_question = str(question or "").strip()
    cleaned_answer = str(answer or "").strip()
    if not cleaned_question or not cleaned_answer:
        return JSONResponse(
            {"status": "error", "detail": "Question and answer are required."},
            status_code=422,
        )

    current_session_id = resolve_chat_session_id(request, session_id)
    feedback_id = await save_user_feedback(
        session_id=current_session_id,
        question=cleaned_question,
        answer=cleaned_answer,
        thumbs_up=thumbs_up,
        comment=comment,
    )
    return JSONResponse(
        {
            "status": "ok",
            "feedback_id": feedback_id,
            "message": "Đã ghi nhận đánh giá.",
        }
    )


@router.get("/source-preview")
async def source_preview_page(request: Request, source: str = ""):
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response

    normalized_source = str(source or "").strip()
    if not normalized_source:
        return HTMLResponse("Missing source.", status_code=400)

    documents, _metadatas = fetch_documents_by_source(normalized_source)
    chunks = [str(document or "").strip() for document in documents if str(document or "").strip()]
    if not chunks:
        return HTMLResponse("Source not found in vector database.", status_code=404)

    shown_chunks = chunks[:20]
    display_source = format_source_label(normalized_source) or normalized_source
    source_title = html.escape(display_source)
    raw_source_html = ""
    if display_source != normalized_source:
        raw_source_html = f'<div class="raw-source">Đường dẫn nội bộ: {html.escape(normalized_source)}</div>'
    chunk_count = len(chunks)
    chunks_html = "\n".join(
        (
            '<section class="chunk">'
            f'<div class="chunk-title">Đoạn {index}</div>'
            f"<pre>{html.escape(chunk)}</pre>"
            "</section>"
        )
        for index, chunk in enumerate(shown_chunks, start=1)
    )
    if chunk_count > len(shown_chunks):
        chunks_html += (
            f'<p class="notice">Đang hiển thị {len(shown_chunks)}/{chunk_count} đoạn đầu tiên '
            "từ vector database.</p>"
        )

    return HTMLResponse(
        f"""<!doctype html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Nguồn tham khảo - ICTU AI</title>
    <style>
        :root {{
            color-scheme: light dark;
            --bg: #f5f7fb;
            --panel: #ffffff;
            --text: #0f172a;
            --muted: #64748b;
            --border: #d8e0ee;
            --primary: #1565c0;
        }}
        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg: #0b1220;
                --panel: #111827;
                --text: #e5edf8;
                --muted: #9aa8bc;
                --border: #263449;
                --primary: #60a5fa;
            }}
        }}
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            font-family: Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
        }}
        main {{
            max-width: 980px;
            margin: 0 auto;
            padding: 28px 18px 48px;
        }}
        .topbar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 18px;
        }}
        a {{ color: var(--primary); font-weight: 700; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        h1 {{
            margin: 0 0 6px;
            font-size: clamp(1.35rem, 2.8vw, 2rem);
            line-height: 1.2;
            overflow-wrap: anywhere;
        }}
        .meta {{
            color: var(--muted);
            font-size: 0.95rem;
        }}
        .raw-source {{
            color: var(--muted);
            font-size: 0.86rem;
            margin-top: 4px;
            overflow-wrap: anywhere;
        }}
        .chunk {{
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            margin-top: 14px;
        }}
        .chunk-title {{
            color: var(--muted);
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.05em;
            margin-bottom: 10px;
            text-transform: uppercase;
        }}
        pre {{
            margin: 0;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            font-family: inherit;
            font-size: 0.98rem;
        }}
        .notice {{
            color: var(--muted);
            margin-top: 16px;
        }}
    </style>
</head>
<body>
    <main>
        <div class="topbar">
            <a href="/chat">&larr; Quay lại chat</a>
        </div>
        <h1>{source_title}</h1>
        <div class="meta">Nguồn tham khảo nội bộ trong vector database. Tổng số đoạn: {chunk_count}.</div>
        {raw_source_html}
        {chunks_html}
    </main>
</body>
</html>"""
    )


@router.get("/admin")
async def admin_index(request: Request):
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response
    return RedirectResponse("/", status_code=303)


@router.get("/admin/vectorstore-status")
async def admin_vectorstore_status(request: Request):
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response

    from services.vector.vectorstore_boot import get_vectorstore_status

    status = get_vectorstore_status()
    return JSONResponse(
        {
            "vectorstore_path": status["vectorstore_path"],
            "exists": status["exists"],
            "collections": status["collections"],
            "chunks": status["chunks"],
            "sqlite_exists": status["sqlite_exists"],
            "file_count": status["file_count"],
            "collection_names": status.get("collection_names", []),
            "bundled_vectorstore_path": status.get("bundled_vectorstore_path"),
            "bundled_sqlite_exists": status.get("bundled_sqlite_exists"),
            "azure": status.get("azure", False),
        }
    )


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


@router.get("/upload")
async def upload_page_alias(request: Request):
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response
    return RedirectResponse("/data-loader", status_code=303)


@router.post("/upload")
@limiter.limit(settings.API_RATE_UPLOAD)
async def upload_files(
    request: Request,
    background_tasks: BackgroundTasks,
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

    result = await get_ingestion_queue().enqueue_upload(
        files=files,
        tool_name=tool_name,
        processor=upload_markdown_files,
        background_tasks=background_tasks,
        client_start_time=client_start_time,
        client_total_size=client_total_size,
    )
    return JSONResponse(result)


@router.get("/upload/status/{job_id}")
async def upload_job_status(request: Request, job_id: str):
    admin_response = _admin_required_json(request)
    if admin_response is not None:
        return admin_response
    return JSONResponse(get_ingestion_queue().get_status(job_id))


@router.get("/upload/progress/{job_id}")
async def upload_job_progress(request: Request, job_id: str):
    admin_response = _admin_required_json(request)
    if admin_response is not None:
        return admin_response
    return StreamingResponse(
        get_ingestion_queue().sse_events(job_id),
        media_type="text/event-stream",
    )


@router.post("/import-qa-corpus")
@limiter.limit(settings.API_RATE_ADMIN)
async def import_qa_corpus(request: Request, csrf_token: str = Form(...), reset_first: bool = Form(False)):
    if not validate_csrf_token(request, csrf_token):
        return JSONResponse({"status": "error", "msg": "CSRF Invalid!"}, status_code=403)
    admin_response = _admin_required_json(request)
    if admin_response is not None:
        return admin_response

    try:
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
    except Exception as exc:
        next_csrf_token = rotate_csrf_token(request)
        return JSONResponse(
            {
                "status": "error",
                "msg": f"Hệ thống gặp lỗi khi import corpus: {exc}",
                "csrf_token": next_csrf_token,
            },
            status_code=500,
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


@router.get("/vector-store")
async def vector_store_alias(request: Request):
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response
    return RedirectResponse("/vector-manager", status_code=303)


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


@router.get("/knowledge")
async def knowledge_alias(request: Request):
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response
    return RedirectResponse("/knowledge-base", status_code=303)


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


@router.get("/settings")
async def settings_alias(request: Request):
    admin_response = _admin_required(request)
    if admin_response is not None:
        return admin_response
    return RedirectResponse("/config", status_code=303)


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
    login_response = _login_required(request)
    if login_response is not None:
        return login_response
    current_role = get_current_role(request)
    current_username = get_current_username(request)
    is_admin = current_role == "admin"
    payload = get_history_page_data(
        page=page,
        per_page=50,
        owner_username=None if is_admin else current_username,
        include_legacy_unowned=not is_admin and settings.SHOW_LEGACY_UNOWNED_CHAT_HISTORY_TO_USERS,
        include_uploaded_files=False,
    )
    payload["csrf_token"] = ensure_csrf_token(request)
    payload["history_scope_label"] = "Tất cả người dùng" if is_admin else "Lịch sử của bạn"
    payload["show_admin_history_tools"] = is_admin
    return render_page(request, HISTORY_TEMPLATE, context=payload)


@router.get("/evaluation-dashboard")
async def evaluation_dashboard_page(request: Request):
    admin_response = _evaluation_dashboard_required(request)
    if admin_response is not None:
        return admin_response
    return FileResponse(EVALUATION_DASHBOARD_HTML)


def register_web_routes(app) -> None:
    app.include_router(router)
