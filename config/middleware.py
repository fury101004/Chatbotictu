from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.client_ip = getattr(record, "client_ip", "-")
        record.method = getattr(record, "method", "-")
        record.url = getattr(record, "url", "-")
        record.status_code = getattr(record, "status_code", "-")
        record.duration = getattr(record, "duration", 0.0)
        return True


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = datetime.now()
        client_ip = request.client.host if request.client else "-"

        try:
            response = await call_next(request)
            status_code = response.status_code
            logging.info(
                "",
                extra={
                    "client_ip": client_ip,
                    "method": request.method,
                    "url": str(request.url),
                    "status_code": status_code,
                    "duration": (datetime.now() - start_time).total_seconds() * 1000,
                },
            )
            return response
        except Exception as exc:
            logging.error(f"ERROR | {client_ip} | {request.method} {request.url} | {exc}")
            raise



def configure_logging() -> None:
    if logging.getLogger().handlers:
        return

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(client_ip)s | %(method)s %(url)s | %(status_code)s | %(duration).2fms",
        handlers=[
            logging.FileHandler("data/api.log"),
            logging.StreamHandler(),
        ],
    )
    request_context_filter = RequestContextFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(request_context_filter)



def escapejs_filter(value):
    return json.dumps(value)[1:-1]



def create_template_engine(directory: str = "templates") -> Jinja2Templates:
    templates = Jinja2Templates(directory=directory)
    templates.env.filters["escapejs"] = escapejs_filter
    return templates



def register_middleware(app: FastAPI) -> None:
    app.add_exception_handler(
        RateLimitExceeded,
        lambda request, exc: JSONResponse(
            status_code=429,
            content={"detail": "Qua nhieu request, thu lai sau nhe!"},
        ),
    )
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(SessionMiddleware, secret_key=secrets.token_hex(32))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(LoggingMiddleware)
