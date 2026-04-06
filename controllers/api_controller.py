from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from config.dependencies import create_partner_token, verify_token
from config.settings import settings
from models.chat import ChatRequest, ChatResponse
from services.chat_service import process_chat_message
from services.document_service import upload_markdown_files
from views.api_view import (
    build_chat_response,
    build_health_response,
    build_token_response,
    build_upload_response,
)
from config.limiter import limiter

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/auth/token")
async def get_token(partner_key: str = Form(...)):
    if partner_key != settings.PARTNER_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid partner key")
    return build_token_response(create_partner_token())


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(settings.API_RATE_CHAT)
async def api_chat(
    request: Request,
    body: ChatRequest,
    token=Depends(verify_token),
):
    result = await process_chat_message(body.message, body.session_id)
    return build_chat_response(result, body.session_id)


@router.post("/upload")
@limiter.limit(settings.API_RATE_UPLOAD)
async def api_upload(
    request: Request,
    files: list[UploadFile] = File(...),
    session_id: Optional[str] = Form(None),
    token=Depends(verify_token),
):
    result = await upload_markdown_files(files=files)
    return build_upload_response(result, session_id)


@router.get("/health")
async def health():
    return build_health_response()



def register_api_routes(app) -> None:
    app.include_router(router)

