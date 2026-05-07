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
from services.content.knowledge_base_service import approve_chat_entry, get_knowledge_base_payload
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


@router.get("/")
async def home(request: Request):
    return render_page(request, HOME_TEMPLATE)


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

    delete_uploaded_document(filename)
    rotate_csrf_token(request)
    return redirect_vector_manager()


@router.get("/get-current-prompt")
async def get_current_prompt_view():
    return current_prompt_response(get_system_prompt())


@router.get("/data-loader")
async def data_loader_page(request: Request):
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

    reset_document_store()
    rotate_csrf_token(request)
    return redirect_vector_manager()


@router.get("/vector-manager")
async def vector_manager(request: Request, limit_per_file: int = 50):
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


@router.get("/config")
async def config_page(request: Request):
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

    try:
        delete_chunk_by_id(chunk_id)
        return {"status": "ok"}
    except Exception:
        return {"status": "error"}


@router.get("/history")
async def history_page(request: Request, page: int = 1):
    payload = get_history_page_data(page=page, per_page=50)
    payload["csrf_token"] = ensure_csrf_token(request)
    return render_page(request, HISTORY_TEMPLATE, context=payload)


def register_web_routes(app) -> None:
    app.include_router(router)

