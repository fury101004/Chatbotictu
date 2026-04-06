from __future__ import annotations

import secrets

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from config.settings import settings
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
from views.web_view import (
    current_prompt_response,
    json_upload_result,
    redirect_vector_manager,
    render_chat_page,
    render_config_page,
    render_data_loader_page,
    render_history_page,
    render_home,
    render_vector_manager_page,
    unauthorized_response,
)
from config.db import get_system_prompt
from services.vector_store_service import get_collection

router = APIRouter()


@router.get("/")
async def home(request: Request):
    return render_home(request)


@router.get("/chat")
async def chat_page(request: Request):
    return render_chat_page(request)


@router.post("/chat")
async def chat_web(message: str = Form(...), session_id: str = Form("default")):
    return await process_chat_message(message, session_id)


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
    return render_data_loader_page(
        request,
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
    )


@router.post("/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    client_start_time: float = Form(None),
    client_total_size: int = Form(None),
):
    result = await upload_markdown_files(
        files=files,
        client_start_time=client_start_time,
        client_total_size=client_total_size,
    )
    return json_upload_result(result)


@router.post("/import-qa-corpus")
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


@router.get("/config")
async def config_page(request: Request):
    payload = get_config_page_payload()
    return render_config_page(request, **payload)


@router.post("/update-config")
async def update_config(
    chunk_size: int = Form(...),
    chunk_overlap: int = Form(...),
    bot_rules: str = Form(...),
    reingest: bool = Form(False),
):
    result = update_runtime_config(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        bot_rules=bot_rules,
        reingest=reingest,
        reingest_callback=reingest_uploaded_documents,
    )
    return JSONResponse(result)


@router.post("/delete-chunk")
async def delete_chunk(chunk_id: str = Form(...)):
    try:
        get_collection().delete(ids=[chunk_id])
        return {"status": "ok"}
    except Exception:
        return {"status": "error"}


@router.get("/history")
async def history_page(request: Request, page: int = 1):
    payload = get_history_page_data(page=page, per_page=50)
    return render_history_page(request, payload=payload)

