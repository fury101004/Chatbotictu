from __future__ import annotations

import secrets
from urllib.parse import quote_plus

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse

from config.rag_tools import DEFAULT_RAG_TOOL, get_upload_tool_options
from config.settings import settings
from config.limiter import limiter
from services.chat_service import process_chat_message
from services.config_service import get_config_page_payload, update_runtime_config
from services.document_service import (
    delete_uploaded_document,
    get_history_page_data,
    import_seed_corpus,
    get_vector_manager_payload,
    reingest_uploaded_documents,
    reset_document_store,
    upload_markdown_files,
)
from services.knowledge_base_service import approve_chat_entry, get_knowledge_base_payload
from services.llm_service import get_chat_model_options
from views.web_view import (
    current_prompt_response,
    json_upload_result,
    redirect_vector_manager,
    render_chat_page,
    render_config_page,
    render_data_loader_page,
    render_history_page,
    render_home,
    render_knowledge_base_page,
    render_vector_manager_page,
    unauthorized_response,
)
from config.system_prompt import get_system_prompt
from services.vector_store_service import get_collection

router = APIRouter()


@router.get("/")
async def home(request: Request):
    return render_home(request)


@router.get("/chat")
async def chat_page(request: Request):
    if "chat_session_id" not in request.session:
        request.session["chat_session_id"] = secrets.token_hex(16)
    return render_chat_page(request, chat_model_options=get_chat_model_options())


@router.post("/chat")
@limiter.limit(settings.API_RATE_CHAT)
async def chat_web(
    request: Request,
    message: str = Form(...),
    session_id: str = Form("default"),
    llm_model: str = Form("auto"),
):
    current_session_id = (session_id or "").strip()
    if not current_session_id or current_session_id == "default":
        current_session_id = str(request.session.get("chat_session_id") or "").strip()
    if not current_session_id:
        current_session_id = secrets.token_hex(16)
        request.session["chat_session_id"] = current_session_id

    return await process_chat_message(message, current_session_id, llm_model=llm_model)


@router.post("/delete-file")
async def delete_file(request: Request, filename: str = Form(...), csrf_token: str = Form(...)):
    if request.session.get("csrf_token") != csrf_token:
        return unauthorized_response("CSRF Invalid!")

    delete_uploaded_document(filename)
    request.session["csrf_token"] = secrets.token_hex(16)
    return redirect_vector_manager()


@router.get("/get-current-prompt")
async def get_current_prompt_view():
    return current_prompt_response(get_system_prompt())


@router.get("/data-loader")
async def data_loader_page(request: Request):
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_hex(16)

    return render_data_loader_page(
        request,
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        tool_options=get_upload_tool_options(),
        default_tool=DEFAULT_RAG_TOOL,
        csrf_token=request.session["csrf_token"],
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
    if request.session.get("csrf_token") != csrf_token:
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
    if request.session.get("csrf_token") != csrf_token:
        return JSONResponse({"status": "error", "msg": "CSRF Invalid!"}, status_code=403)

    result = import_seed_corpus(reset_first=reset_first)
    request.session["csrf_token"] = secrets.token_hex(16)

    status_code = 200 if result.get("status") in {"success", "partial"} else 500
    return JSONResponse(
        {
            **result,
            "csrf_token": request.session["csrf_token"],
        },
        status_code=status_code,
    )


@router.post("/reset-vectorstore")
@limiter.limit(settings.API_RATE_ADMIN)
async def reset_vs(request: Request, csrf_token: str = Form(...)):
    if request.session.get("csrf_token") != csrf_token:
        return unauthorized_response()

    reset_document_store()
    request.session["csrf_token"] = secrets.token_hex(16)
    return redirect_vector_manager()


@router.get("/vector-manager")
async def vector_manager(request: Request, limit_per_file: int = 50):
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_hex(16)

    payload = get_vector_manager_payload(limit_per_file)
    return render_vector_manager_page(
        request,
        payload=payload,
        csrf_token=request.session["csrf_token"],
    )


@router.get("/knowledge-base")
async def knowledge_base_page(
    request: Request,
    q: str = "",
    limit: int = 18,
    status: str = "",
    message: str = "",
):
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_hex(16)

    payload = get_knowledge_base_payload(query=q, limit=limit)
    payload["csrf_token"] = request.session["csrf_token"]
    payload["flash_status"] = status
    payload["flash_message"] = message
    return render_knowledge_base_page(request, payload=payload)


@router.post("/knowledge-base/approve-chat")
@limiter.limit(settings.API_RATE_ADMIN)
async def approve_chat_to_knowledge_base(
    request: Request,
    entry_id: str = Form(...),
    tool_name: str = Form(DEFAULT_RAG_TOOL),
    return_q: str = Form(""),
    csrf_token: str = Form(...),
):
    if request.session.get("csrf_token") != csrf_token:
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

    request.session["csrf_token"] = secrets.token_hex(16)
    return RedirectResponse(redirect_url, status_code=303)


@router.get("/config")
async def config_page(request: Request):
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_hex(16)
    payload = get_config_page_payload()
    return render_config_page(request, csrf_token=request.session["csrf_token"], **payload)


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
    if request.session.get("csrf_token") != csrf_token:
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
    if request.session.get("csrf_token") != csrf_token:
        return JSONResponse({"status": "error", "error": "CSRF Invalid!"}, status_code=403)

    try:
        get_collection().delete(ids=[chunk_id])
        return {"status": "ok"}
    except Exception:
        return {"status": "error"}


@router.get("/history")
async def history_page(request: Request, page: int = 1):
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_hex(16)

    payload = get_history_page_data(page=page, per_page=50)
    payload["csrf_token"] = request.session["csrf_token"]
    return render_history_page(request, payload=payload)

