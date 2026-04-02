from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_or_create_user_id
from app.services.history_service import (
    PdfExportUnavailableError,
    clear_user_history,
    export_history_as_pdf,
    export_history_as_txt,
    list_history_for_api,
)


router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
def api_history(request: Request):
    user_id = get_or_create_user_id(request)
    return list_history_for_api(user_id)


@router.post("/clear")
def api_clear_history(request: Request):
    user_id = get_or_create_user_id(request)
    clear_user_history(user_id)
    return {"status": "ok"}


@router.get("/export/txt")
def export_txt(request: Request):
    user_id = get_or_create_user_id(request)
    buffer = export_history_as_txt(user_id)
    headers = {"Content-Disposition": 'attachment; filename="chat_history.txt"'}
    return StreamingResponse(buffer, media_type="text/plain; charset=utf-8", headers=headers)


@router.get("/export/pdf")
def export_pdf(request: Request):
    user_id = get_or_create_user_id(request)
    try:
        buffer = export_history_as_pdf(user_id)
    except PdfExportUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    headers = {"Content-Disposition": 'attachment; filename="chat_history.pdf"'}
    return StreamingResponse(buffer, media_type="application/pdf", headers=headers)
