from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config.limiter import limiter
from config.middleware import configure_logging, create_template_engine, register_middleware
from config.settings import settings
from controllers.api_controller import register_api_routes
from controllers.web_controller import register_web_routes


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(title=settings.APP_NAME)
    app.state.limiter = limiter
    app.state.templates = create_template_engine(settings.FRONTEND_TEMPLATE_DIR)

    register_middleware(app)
    app.mount("/static", StaticFiles(directory=settings.FRONTEND_ASSET_DIR), name="static")

    register_web_routes(app)
    register_api_routes(app)

    return app
