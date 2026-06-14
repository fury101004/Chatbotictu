from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from services.admin_auth_service import is_admin_authenticated, is_web_authenticated
from services.eval_tracker import get_eval_tracker

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _require_admin(request: Request) -> None:
    if not is_web_authenticated(request):
        raise HTTPException(status_code=401, detail="Login required")
    if not is_admin_authenticated(request):
        raise HTTPException(status_code=403, detail="Admin role required")


@router.get("/metrics")
async def dashboard_metrics(request: Request):
    _require_admin(request)
    return await get_eval_tracker().metrics(hours=24)


@router.get("/export")
async def dashboard_export(request: Request):
    _require_admin(request)
    csv_text = await get_eval_tracker().export_csv()
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="eval_log.csv"'},
    )


@router.get("")
async def dashboard_home(request: Request):
    _require_admin(request)
    return RedirectResponse("/evaluation-dashboard", status_code=307)


def register_dashboard_routes(app) -> None:
    app.include_router(router)
