from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config.middleware import configure_logging, create_template_engine, register_middleware
from controllers.api_controller import register_api_routes
from controllers.web_controller import router as web_router
from services.cskh_service import register_cskh_routes
from config.limiter import limiter


FRONTEND_TEMPLATE_DIR = "views/frontend/templates"
FRONTEND_ASSET_DIR = "views/frontend/assets"


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(title="Tro ly ao Hidemium AI")
    app.state.limiter = limiter
    app.state.templates = create_template_engine(FRONTEND_TEMPLATE_DIR)
    app.state.cskh_routes_registered = False

    register_middleware(app)
    app.mount("/static", StaticFiles(directory=FRONTEND_ASSET_DIR), name="static")

    app.include_router(web_router)
    register_api_routes(app)

    @app.on_event("startup")
    async def startup_event():
        if not app.state.cskh_routes_registered:
            await register_cskh_routes(app, app.state.templates)
            app.state.cskh_routes_registered = True

    return app
