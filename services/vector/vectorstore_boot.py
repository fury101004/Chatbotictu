from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from config.settings import settings

COLLECTION_NAME = "markdown_docs_v2"


def get_vectorstore_dir() -> Path:
    """Single source of truth for Chroma persistence directory."""
    return Path(settings.VECTORSTORE_DIR).resolve()


def get_bundled_vectorstore_dir() -> Path:
    return (settings.PROJECT_ROOT / "vectorstore").resolve()


def count_files_in_dir(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(1 for item in path.rglob("*") if item.is_file())


def get_vectorstore_status() -> dict[str, Any]:
    vectorstore_dir = get_vectorstore_dir()
    sqlite_path = vectorstore_dir / "chroma.sqlite3"
    bundled_dir = get_bundled_vectorstore_dir()
    bundled_sqlite = bundled_dir / "chroma.sqlite3"

    status: dict[str, Any] = {
        "vectorstore_path": str(vectorstore_dir),
        "bundled_vectorstore_path": str(bundled_dir),
        "exists": vectorstore_dir.is_dir(),
        "sqlite_exists": sqlite_path.is_file(),
        "bundled_sqlite_exists": bundled_sqlite.is_file(),
        "file_count": count_files_in_dir(vectorstore_dir),
        "collections": 0,
        "chunks": 0,
        "collection_names": [],
        "azure": bool(os.getenv("WEBSITE_SITE_NAME")),
        "env_vectorstore_dir": os.getenv("VECTORSTORE_DIR", ""),
    }

    try:
        from services.vector.vector_store_service import get_client

        client = get_client()
        collections = client.list_collections()
        status["collection_names"] = [collection.name for collection in collections]
        status["collections"] = len(collections)

        total_chunks = 0
        primary_chunks = 0
        for collection in collections:
            count = collection.count()
            total_chunks += count
            if collection.name == COLLECTION_NAME:
                primary_chunks = count
        status["chunks"] = primary_chunks or total_chunks
    except Exception as exc:
        status["error"] = str(exc)

    return status


def log_vectorstore_boot_status() -> dict[str, Any]:
    status = get_vectorstore_status()
    print(f"[BOOT] VECTORSTORE_DIR={status['vectorstore_path']}")
    print(f"[BOOT] bundled_vectorstore={status['bundled_vectorstore_path']}")
    print(f"[BOOT] chroma.sqlite3 exists={status['sqlite_exists']}")
    print(f"[BOOT] bundled chroma.sqlite3 exists={status['bundled_sqlite_exists']}")
    print(f"[BOOT] files_in_vectorstore={status['file_count']}")
    print(f"[BOOT] collections={status['collections']}")
    print(f"[BOOT] chunks={status['chunks']}")
    if status.get("collection_names"):
        print(f"[BOOT] collection_names={status['collection_names']}")
    if status.get("error"):
        print(f"[BOOT] vectorstore probe error: {status['error']}")
    return status
