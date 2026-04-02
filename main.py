from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api import api_router
from app.core.config import (
    APP_DESCRIPTION,
    APP_DEBUG,
    APP_NAME,
    SECRET_KEY,
    SERVER_HOST,
    SERVER_PORT,
    SESSION_COOKIE_NAME,
    SESSION_HTTPS_ONLY,
    SESSION_SAME_SITE,
    STATIC_DIR,
    UVICORN_RELOAD,
)
from app.models.history import init_db
from app.web import web_router


def create_app() -> FastAPI:
    application = FastAPI(
        title=APP_NAME,
        description=APP_DESCRIPTION,
        debug=APP_DEBUG,
    )
    application.add_middleware(
        SessionMiddleware,
        secret_key=SECRET_KEY,
        session_cookie=SESSION_COOKIE_NAME,
        same_site=SESSION_SAME_SITE,
        https_only=SESSION_HTTPS_ONLY,
    )
    application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    init_db()

    application.include_router(web_router)
    application.include_router(api_router)
    return application


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=UVICORN_RELOAD,
    )


if __name__ == "__main__":
    main()
