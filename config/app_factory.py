from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config.limiter import limiter
from config.middleware import configure_logging, create_template_engine, register_middleware
from config.settings import settings
from controllers.api_controller import register_api_routes
from controllers.cskh_controller import register_cskh_routes
from controllers.web_controller import register_web_routes


@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    if not app.state.cskh_routes_registered:
        await register_cskh_routes(app, app.state.templates)
        app.state.cskh_routes_registered = True
    yield


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(title=settings.APP_NAME, lifespan=_app_lifespan)
    app.state.limiter = limiter
    app.state.templates = create_template_engine(settings.FRONTEND_TEMPLATE_DIR)
    app.state.cskh_routes_registered = False

    register_middleware(app)
    app.mount("/static", StaticFiles(directory=settings.FRONTEND_ASSET_DIR), name="static")

    register_web_routes(app)
    register_api_routes(app)

    return app
