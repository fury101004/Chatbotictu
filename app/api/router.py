from fastapi import APIRouter

from app.api.routes.chat import router as chat_router
from app.api.routes.history import router as history_router
from app.api.routes.knowledge import router as knowledge_router


api_router = APIRouter()
api_router.include_router(chat_router)
api_router.include_router(history_router)
api_router.include_router(knowledge_router)
