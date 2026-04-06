from __future__ import annotations

import shutil
import sqlite3
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.settings import settings
from models.document import HistoryEntry, UploadBatchResult, VectorManagerPayload
from config.db import add_uploaded_file, clear_uploaded_files, delete_uploaded_file, get_uploaded_files
from services.vector_store_service import add_documents, get_collection, reset_vectorstore

SUPPORTED_TEXT_SUFFIXES = {".md", ".markdown", ".txt"}


def _iter_importable_paths(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_TEXT_SUFFIXES
    )


async def upload_markdown_files(
    files: list,
    client_start_time: Optional[float] = None,
    client_total_size: Optional[int] = None,
) -> dict:
    t0 = time.time()
    total_upload_size = 0
    success_files: list[str] = []
    updated_files: list[str] = []
    failed_files: list[str] = []

    real_speed = None
    if client_start_time and client_total_size and client_start_time > 0:
        duration_from_client = t0 - (client_start_time / 1000.0)
        if duration_from_client > 0:
            real_speed = client_total_size / duration_from_client / 1024 / 1024
            print(
                f"UPLOAD TU CLIENT: {real_speed:.2f} MB/s "
                f"({client_total_size/1024/1024:.1f} MB trong {duration_from_client:.2f}s)"
            )

    coll = get_collection()
    existing = coll.get(include=["metadatas"])
    existing_sources = {m.get("source") for m in existing.get("metadatas", []) if m}

    for file in files:
        filename = file.filename
        if not filename.lower().endswith((".md", ".markdown", ".txt")):
            failed_files.append(f"{filename} -> chi ho tro .md/.txt")
            continue

        try:
            t_read = time.time()
            content = await file.read()
            total_upload_size += len(content)
            text = content.decode("utf-8", errors="ignore")
            read_speed = len(content) / max(time.time() - t_read, 1e-6) / 1024 / 1024
            print(f"[DOC FILE] {filename}: {read_speed:.2f} MB/s ({len(content)/1024/1024:.2f} MB)")

            if filename in existing_sources:
                coll.delete(where={"source": filename})
                updated_files.append(filename)
            else:
                success_files.append(filename)

            t_chunk = time.time()
            add_documents(text, filename)
            chunk_speed = len(content) / max(time.time() - t_chunk, 1e-6) / 1024 / 1024
            print(f"[CHUNK + ADD] {filename}: {chunk_speed:.2f} MB/s")

            file_path = settings.UPLOAD_DIR / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)

            uploaded_names = {item["filename"] for item in get_uploaded_files()}
            if filename not in uploaded_names:
                add_uploaded_file(filename)
        except Exception as exc:
            print(f"[LOI] {filename}: {exc}")
            failed_files.append(f"{filename} -> loi: {exc}")

    total_time = time.time() - t0
    avg_speed = total_upload_size / max(total_time, 1e-6) / 1024 / 1024
    print(
        f"HOAN TAT XU LY: {avg_speed:.2f} MB/s trung binh "
        f"({total_upload_size/1024/1024:.1f} MB trong {total_time:.2f}s)"
    )

    result = UploadBatchResult(
        added=len(success_files),
        updated=len(updated_files),
        failed=len(failed_files),
        msg=(
            "<strong>HOAN TAT!</strong><br>"
            f"Them: {len(success_files)} | Cap nhat: {len(updated_files)} | Loi: {len(failed_files)}"
        ),
        real_speed=f"{real_speed:.2f}" if real_speed else None,
        detail={
            "added": success_files,
            "updated": updated_files,
            "failed": failed_files,
        },
    )
    return result.to_dict()


def import_seed_corpus(reset_first: bool = False) -> dict:
    root = settings.QA_CORPUS_ROOT
    if not root.exists():
        return {
            "status": "error",
            "msg": f"Khong tim thay thu muc corpus: {root}",
            "total_files": 0,
            "imported_files": 0,
            "failed_files": 0,
            "total_chunks": get_collection().count(),
        }

    corpus_paths = _iter_importable_paths(root)
    if not corpus_paths:
        return {
            "status": "error",
            "msg": f"Thu muc {root} chua co file .md/.txt de import",
            "total_files": 0,
            "imported_files": 0,
            "failed_files": 0,
            "total_chunks": get_collection().count(),
        }

    if reset_first:
        reset_vectorstore()

    coll = get_collection()
    imported_files = 0
    failed_sources: list[str] = []

    for path in corpus_paths:
        source_name = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            add_documents(
                file_content=text,
                filename=path.name,
                source_name=source_name,
            )
            imported_files += 1
        except Exception as exc:
            print(f"[IMPORT QA CORPUS LOI] {source_name}: {exc}")
            failed_sources.append(source_name)

    total_chunks = coll.count()
    status = "success" if imported_files > 0 and not failed_sources else "partial" if imported_files > 0 else "error"
    action = "Reset + import" if reset_first else "Import"
    msg = (
        f"{action} xong: {imported_files}/{len(corpus_paths)} file tu qa_generated_fixed. "
        f"Vector store hien co {total_chunks} chunks."
    )
    if failed_sources:
        msg += f" Loi: {len(failed_sources)} file."

    return {
        "status": status,
        "msg": msg,
        "total_files": len(corpus_paths),
        "imported_files": imported_files,
        "failed_files": len(failed_sources),
        "failed_sources": failed_sources[:20],
        "total_chunks": total_chunks,
    }


def delete_uploaded_document(filename: str) -> None:
    (settings.UPLOAD_DIR / filename).unlink(missing_ok=True)
    delete_uploaded_file(filename)
    get_collection().delete(where={"source": filename})



def reset_document_store() -> None:
    reset_vectorstore()
    if settings.UPLOAD_DIR.exists():
        shutil.rmtree(settings.UPLOAD_DIR)
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    clear_uploaded_files()



def get_vector_manager_payload(limit_per_file: int = 50) -> dict:
    coll = get_collection()
    data = coll.get(include=["metadatas", "documents"])

    chunks_by_file: dict[str, list[dict]] = defaultdict(list)
    for doc_id, doc, meta in zip(data["ids"], data.get("documents", []), data["metadatas"]):
        source = meta.get("source", "unknown.md")
        preview_text = " ".join(doc.strip().split()[:30])
        if len(doc.strip().split()) > 30:
            preview_text += "..."

        chunks_by_file[source].append(
            {
                "id": doc_id,
                "content": doc.strip(),
                "preview": preview_text,
                "title": meta.get("title", "Khong co tieu de"),
                "level": meta.get("level", 1),
                "word_count": len(doc.split()),
            }
        )

    for source in chunks_by_file:
        chunks_by_file[source].sort(key=lambda item: item["level"], reverse=True)
        chunks_by_file[source] = chunks_by_file[source][:limit_per_file]

    payload = VectorManagerPayload(
        chunks_by_file=dict(chunks_by_file),
        total_chunks=sum(len(items) for items in chunks_by_file.values()),
        total_files=len(chunks_by_file),
    )
    return payload.to_dict()



def reingest_uploaded_documents() -> tuple[int, int]:
    uploaded_paths = [
        path
        for path in settings.UPLOAD_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt"}
    ] if settings.UPLOAD_DIR.exists() else []

    if not uploaded_paths:
        return 0, 0

    reset_vectorstore()
    total_files = 0
    total_chunks = 0
    coll = get_collection()

    for path in uploaded_paths:
        try:
            before_count = coll.count()
            text = path.read_text(encoding="utf-8")
            add_documents(text, path.name)
            total_files += 1
            total_chunks += max(coll.count() - before_count, 0)
        except Exception as exc:
            print(f"Re-ingest loi {path.name}: {exc}")

    return total_files, total_chunks



def get_history_page_data(page: int, per_page: int = 50) -> dict:
    offset = (page - 1) * per_page
    conn = sqlite3.connect("data/bot_config.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM chat_history")
    total = cursor.fetchone()[0]
    total_pages = max(1, (total + per_page - 1) // per_page)
    cursor.execute(
        "SELECT role, content, timestamp FROM chat_history ORDER BY id DESC LIMIT ? OFFSET ?",
        (per_page, offset),
    )
    rows = cursor.fetchall()
    conn.close()

    history: list[HistoryEntry] = []
    for role, content, ts in rows:
        try:
            time_str = datetime.strptime(ts.split(".")[0], "%Y-%m-%d %H:%M:%S").strftime("%d/%m %H:%M")
        except Exception:
            time_str = "Vua xong"
        history.append(HistoryEntry(role=role, content=content, time=time_str))

    return {
        "history": [{"role": entry.role, "content": entry.content, "time": entry.time} for entry in history],
        "uploaded_files": get_uploaded_files(),
        "page": page,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
    }






