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

    vectorstore_status: dict = {}
    try:
        from services.vector.vectorstore_boot import get_vectorstore_status

        vectorstore_status = get_vectorstore_status()
    except Exception as exc:
        vectorstore_status = {"error": str(exc)}

    checks = {
        "data_dir_exists": _directory_exists(data_dir),
        "data_dir_writable": _directory_writable(data_dir),
        "vectorstore_dir_exists": _directory_exists(vectorstore_dir),
        "vectorstore_dir_writable": _directory_writable(vectorstore_dir),
        "log_dir_exists": _directory_exists(log_dir),
        "log_dir_writable": _directory_writable(log_dir),
        "llm_configured": configured_model is not None,
        "embedding_backend_ready": embedding_backend_ready(),
        "vectorstore_sqlite_exists": bool(vectorstore_status.get("sqlite_exists")),
        "vectorstore_chunks_gt_zero": int(vectorstore_status.get("chunks") or 0) > 0,
    }

    return {
        "app_name": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "port": os.getenv("PORT", "8000"),
        "data_dir": str(data_dir),
        "vectorstore_dir": str(vectorstore_dir),
        "db_path": str(settings.DB_PATH),
        "rag_upload_root": str(settings.RAG_UPLOAD_ROOT),
        "log_dir": str(log_dir),
        "vectorstore": {
            "path": vectorstore_status.get("vectorstore_path", str(vectorstore_dir)),
            "exists": vectorstore_status.get("exists", False),
            "sqlite_exists": vectorstore_status.get("sqlite_exists", False),
            "collections": vectorstore_status.get("collections", 0),
            "chunks": vectorstore_status.get("chunks", 0),
            "file_count": vectorstore_status.get("file_count", 0),
            "bundled_sqlite_exists": vectorstore_status.get("bundled_sqlite_exists", False),
            "error": vectorstore_status.get("error"),
        },
        "checks": checks,
        "status": "ready" if all(checks.values()) else "degraded",
        "timestamp": datetime.now().isoformat(),
    }

