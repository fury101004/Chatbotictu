from __future__ import annotations

import hmac
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from config.dependencies import create_partner_token, verify_token
from config.limiter import limiter
from config.rag_tools import DEFAULT_RAG_TOOL
from config.settings import settings
from models.auth import RegisterRequest, RegisterResponse
from models.chat import ChatRequest, ChatResponse
from services.admin_auth_service import is_admin_authenticated, is_web_authenticated, register_web_user
from services.chat.chat_service import process_chat_message
from services.content.document_service import upload_markdown_files
from services.content.knowledge_base_service import get_knowledge_base_payload
from services.evaluation_question_service import get_evaluation_test_questions
from services.eval_tracker import get_eval_tracker
from services.llm.rate_limit_monitor import reset_429_stats, snapshot_429_stats
from services.user_feedback_service import get_feedback_summary
from views.api_view import (
    build_chat_response,
    build_deployment_status_response,
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
@limiter.limit(settings.API_RATE_TOKEN)
async def get_token(request: Request, partner_key: str = Form(...)):
    del request
    if not hmac.compare_digest(str(partner_key), settings.PARTNER_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid partner key")
    return build_token_response(create_partner_token())


@router_api.post("/register", response_model=RegisterResponse)
@limiter.limit(settings.API_RATE_ADMIN)
async def api_register(request: Request, body: RegisterRequest):
    del request
    result = register_web_user(
        full_name=body.full_name,
        username=body.username,
        password=body.password,
        confirm_password=body.confirm_password,
    )
    if not result.ok:
        status_code = 409 if result.code == "duplicate" else 422
        raise HTTPException(status_code=status_code, detail=result.message)
    return RegisterResponse(status="ok", message=result.message)


def _require_admin_session(request: Request) -> None:
    if not is_web_authenticated(request):
        raise HTTPException(status_code=401, detail="Login required")
    if not is_admin_authenticated(request):
        raise HTTPException(status_code=403, detail="Admin role required")


@router_api.get("/logs")
async def api_eval_logs(request: Request, limit: int = 500):
    _require_admin_session(request)
    return await get_eval_tracker().logs(limit=limit)


@router_api.get("/metrics")
async def api_eval_metrics(request: Request, hours: int = 24):
    _require_admin_session(request)
    return await get_eval_tracker().metrics(hours=hours)


@router_api.get("/test-questions")
async def api_eval_test_questions(request: Request):
    _require_admin_session(request)
    return get_evaluation_test_questions()


@router_api.get("/feedback/summary")
async def api_feedback_summary(request: Request):
    _require_admin_session(request)
    return await get_feedback_summary()


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


@router_v1.get("/deployment/status")
@router_api.get("/deployment/status")
async def deployment_status():
    return build_deployment_status_response()


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

