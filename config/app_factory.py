from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config.limiter import limiter
from config.middleware import configure_logging, create_template_engine, register_middleware
from config.settings import settings
from controllers.api_controller import register_api_routes
from controllers.web_controller import register_web_routes
from middleware.input_guard import InputGuardMiddleware
from routers.dashboard import register_dashboard_routes
from services.runtime_config_manager import apply_runtime_config


logger = logging.getLogger(__name__)


def _sync_seed_corpus_on_startup() -> None:
    if not settings.is_production:
        return

    try:
        from services.content.document_service import sync_seed_corpus_index

        result = sync_seed_corpus_index()
        logger.info("Seed corpus sync: %s", result.get("msg", "done"))
    except Exception:
        logger.exception("Seed corpus sync failed during app startup")


def create_app() -> FastAPI:
    configure_logging()
    apply_runtime_config()

    app = FastAPI(title=settings.APP_NAME)
    app.state.limiter = limiter
    app.state.templates = create_template_engine(settings.FRONTEND_TEMPLATE_DIR)

    register_middleware(app)
    app.add_middleware(
        InputGuardMiddleware,
        max_message_chars=settings.MAX_CHAT_MESSAGE_CHARS,
        max_upload_bytes=settings.MAX_UPLOAD_FILE_SIZE_BYTES,
        token_limit=20,
        token_window_seconds=60,
    )
    app.mount("/static", StaticFiles(directory=settings.FRONTEND_ASSET_DIR), name="static")

    register_web_routes(app)
    register_api_routes(app)
    register_dashboard_routes(app)
    _sync_seed_corpus_on_startup()

    return app
