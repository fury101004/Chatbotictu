from __future__ import annotations

import os
import logging
import threading

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


def _is_hosted_azure_app() -> bool:
    return bool(os.getenv("WEBSITE_SITE_NAME") or os.getenv("WEBSITE_INSTANCE_ID"))


def _sync_seed_corpus_on_startup() -> None:
    if not (settings.is_production or _is_hosted_azure_app()):
        return

    try:
        from services.vector.vectorstore_boot import log_vectorstore_boot_status

        log_vectorstore_boot_status()
    except Exception:
        logger.exception("Vector store boot logging failed during app startup")

    def _background_sync() -> None:
        try:
            from services.content.document_service import sync_seed_corpus_index

            logger.info("Seed corpus sync starting in background...")
            result = sync_seed_corpus_index()
            logger.info("Seed corpus sync: %s", result.get("msg", "done"))
        except Exception:
            logger.exception("Seed corpus sync failed during app startup")

    t = threading.Thread(target=_background_sync, daemon=True, name="seed-corpus-sync")
    t.start()
    logger.info("Seed corpus sync dispatched to background thread")


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
