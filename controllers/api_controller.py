from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from config.dependencies import create_partner_token, verify_token
from config.limiter import limiter
from config.rag_tools import DEFAULT_RAG_TOOL
from config.settings import settings
from models.chat import ChatRequest, ChatResponse
from services.chat_service import process_chat_message
from services.document_service import upload_markdown_files
from services.knowledge_base_service import get_knowledge_base_payload
from services.rate_limit_monitor import reset_429_stats, snapshot_429_stats
from views.api_view import (
    build_chat_response,
    build_health_response,
    build_knowledge_base_response,
    build_token_response,
    build_upload_response,
)


router_v1 = APIRouter(prefix="/api/v1", tags=["chat"])
router_api = APIRouter(prefix="/api", tags=["chat"])
router_root = APIRouter(tags=["system"])


@router_v1.post("/auth/token")
@router_api.post("/auth/token")
async def get_token(partner_key: str = Form(...)):
    if partner_key != settings.PARTNER_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid partner key")
    return build_token_response(create_partner_token())


@router_v1.post("/chat", response_model=ChatResponse)
@router_api.post("/chat", response_model=ChatResponse)
@limiter.limit(settings.API_RATE_CHAT)
async def api_chat(
    request: Request,
    body: ChatRequest,
    token=Depends(verify_token),
):
    del token
    result = await process_chat_message(body.message, body.session_id, llm_model=body.llm_model or "auto")
    return build_chat_response(result, body.session_id)


@router_v1.post("/upload")
@limiter.limit(settings.API_RATE_UPLOAD)
async def api_upload(
    request: Request,
    files: list[UploadFile] = File(...),
    tool_name: str = Form(DEFAULT_RAG_TOOL),
    session_id: Optional[str] = Form(None),
    token=Depends(verify_token),
):
    del request, token
    result = await upload_markdown_files(files=files, tool_name=tool_name)
    return build_upload_response(result, session_id)


@router_v1.get("/knowledge-base")
async def api_knowledge_base(
    q: str = "",
    limit: int = 18,
    token=Depends(verify_token),
):
    del token
    payload = get_knowledge_base_payload(query=q, limit=limit)
    return build_knowledge_base_response(payload)


@router_v1.get("/health")
@router_api.get("/health")
@router_root.get("/health")
async def health():
    return build_health_response()


@router_v1.get("/metrics/rate-limit-429")
async def rate_limit_metrics(
    token=Depends(verify_token),
    limit_recent: int = 40,
):
    del token
    return snapshot_429_stats(limit_recent=limit_recent)


@router_v1.post("/metrics/rate-limit-429/reset")
async def reset_rate_limit_metrics(token=Depends(verify_token)):
    del token
    reset_429_stats()
    return {"status": "ok"}


def register_api_routes(app) -> None:
    app.include_router(router_v1)
    app.include_router(router_api)
    app.include_router(router_root)
