from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config.middleware import configure_logging, create_template_engine, register_middleware
from controllers.api_controller import register_api_routes
from controllers.cskh_controller import register_cskh_routes
from controllers.web_controller import register_web_routes
from config.limiter import limiter


FRONTEND_TEMPLATE_DIR = "views/frontend/templates"
FRONTEND_ASSET_DIR = "views/frontend/assets"


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(title="Tro ly ao ICTU AI")
    app.state.limiter = limiter
    app.state.templates = create_template_engine(FRONTEND_TEMPLATE_DIR)
    app.state.cskh_routes_registered = False

    register_middleware(app)
    app.mount("/static", StaticFiles(directory=FRONTEND_ASSET_DIR), name="static")

    register_web_routes(app)
    register_api_routes(app)

    @app.on_event("startup")
    async def startup_event():
        if not app.state.cskh_routes_registered:
            await register_cskh_routes(app, app.state.templates)
            app.state.cskh_routes_registered = True

    return app
