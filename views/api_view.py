from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.settings import settings
from services.vector.vectorstore_boot import get_vectorstore_dir
from models.chat import ChatResponse
from services.llm.llm_service import PRIMARY_MODEL_NAME, get_model
from services.vector.vector_store_service import embedding_backend_ready


def build_token_response(token: str) -> dict:
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 86400,
    }


def build_chat_response(result: dict, session_id: str) -> ChatResponse:
    return ChatResponse(
        **result,
        timestamp=datetime.now().isoformat(),
        session_id=session_id,
    )


def build_upload_response(result: dict, session_id: Optional[str]) -> dict:
    return {
        "status": result.get("status", "success"),
        **result,
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
    }


def build_knowledge_base_response(payload: dict) -> dict:
    return {
        **payload,
        "timestamp": datetime.now().isoformat(),
    }


def build_health_response() -> dict:
    configured_model = get_model()
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "model": PRIMARY_MODEL_NAME,
        "llm_configured": configured_model is not None,
        "embedding_backend_ready": embedding_backend_ready(),
        "timestamp": datetime.now().isoformat(),
    }


def _directory_exists(path: Path) -> bool:
    return path.exists() and path.is_dir()


def _directory_writable(path: Path) -> bool:
    if not _directory_exists(path):
        return False
    probe = path / f".readiness-{uuid.uuid4().hex}.tmp"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def build_deployment_status_response() -> dict:
    data_dir = Path(settings.DATA_DIR)
    vectorstore_dir = get_vectorstore_dir()
    log_dir = Path(settings.LOG_DIR)
    configured_model = get_model()

    checks = {
        "data_dir_exists": _directory_exists(data_dir),
        "data_dir_writable": _directory_writable(data_dir),
        "vectorstore_dir_exists": _directory_exists(vectorstore_dir),
        "vectorstore_dir_writable": _directory_writable(vectorstore_dir),
        "log_dir_exists": _directory_exists(log_dir),
        "log_dir_writable": _directory_writable(log_dir),
        "llm_configured": configured_model is not None,
        "embedding_backend_ready": embedding_backend_ready(),
    }

    return {
        "app_name": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "port": os.getenv("PORT", "8000"),
        "data_dir": str(data_dir),
        "vectorstore_dir": str(vectorstore_dir),
        "log_dir": str(log_dir),
        "checks": checks,
        "status": "ready" if all(checks.values()) else "degraded",
        "timestamp": datetime.now().isoformat(),
    }

