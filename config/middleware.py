from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from config.settings import settings
from services.rate_limit_monitor import record_429


APP_LOG_FORMAT = (
    "%(asctime)s | %(levelname)s | %(client_ip)s | %(method)s %(url)s | "
    "%(status_code)s | %(duration).2fms | %(message)s"
)
APP_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")
app_logger = logging.getLogger("app")


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
            app_logger.info(
                "request completed",
                extra={
                    "client_ip": client_ip,
                    "method": request.method,
                    "url": str(request.url),
                    "status_code": status_code,
                    "duration": (datetime.now() - start_time).total_seconds() * 1000,
                },
            )
            return response
        except Exception:
            app_logger.exception(
                "request failed",
                extra={
                    "client_ip": client_ip,
                    "method": request.method,
                    "url": str(request.url),
                },
            )
            raise


def _has_request_context_filter(handler: logging.Handler) -> bool:
    return any(isinstance(filter_, RequestContextFilter) for filter_ in handler.filters)


def _handler_points_to(handler: logging.Handler, log_path: Path) -> bool:
    if not isinstance(handler, logging.FileHandler):
        return False
    return Path(handler.baseFilename).resolve() == log_path.resolve()


def _ensure_file_handler(
    logger: logging.Logger,
    log_path: Path,
    formatter: logging.Formatter,
    request_context_filter: RequestContextFilter,
) -> None:
    for handler in logger.handlers:
        if _handler_points_to(handler, log_path):
            if not _has_request_context_filter(handler):
                handler.addFilter(request_context_filter)
            return

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(request_context_filter)
    logger.addHandler(file_handler)


def configure_logging() -> None:
    log_path = settings.API_LOG_PATH.resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(APP_LOG_FORMAT)
    request_context_filter = RequestContextFilter()
    root_logger = logging.getLogger()

    root_logger.setLevel(logging.INFO)

    if not root_logger.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(formatter)
        stream_handler.addFilter(request_context_filter)
        root_logger.addHandler(stream_handler)

    for handler in root_logger.handlers:
        if not _has_request_context_filter(handler):
            handler.addFilter(request_context_filter)

    _ensure_file_handler(root_logger, log_path, formatter, request_context_filter)

    for logger_name in APP_LOGGERS:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)

        for handler in logger.handlers:
            if not _has_request_context_filter(handler):
                handler.addFilter(request_context_filter)

        if logger.propagate:
            continue

        _ensure_file_handler(logger, log_path, formatter, request_context_filter)


def escapejs_filter(value):
    return json.dumps(value)[1:-1]


def create_template_engine(directory: str = "templates") -> Jinja2Templates:
    templates = Jinja2Templates(directory=directory)
    templates.env.filters["escapejs"] = escapejs_filter
    return templates


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    client_ip = request.client.host if request.client else "-"
    record_429(
        "api_rate_limiter",
        detail=str(exc),
        metadata={
            "path": request.url.path,
            "method": request.method,
            "client_ip": client_ip,
        },
    )
    response = JSONResponse(
        status_code=429,
        content={"detail": "Qua nhieu request, thu lai sau nhe!"},
    )
    response.headers["Retry-After"] = "60"
    return response


def register_middleware(app: FastAPI) -> None:
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(LoggingMiddleware)
