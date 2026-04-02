from fastapi import APIRouter

from app.web.routes.pages import router as pages_router


web_router = APIRouter()
web_router.include_router(pages_router)
