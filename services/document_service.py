from __future__ import annotations

import shutil
import sqlite3
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Optional

from config.db import add_uploaded_file, clear_uploaded_files, delete_uploaded_file, get_uploaded_files
from config.rag_tools import (
    DEFAULT_RAG_TOOL,
    RAG_TOOL_ORDER,
    RAG_TOOL_PROFILES,
    UPLOAD_SOURCE_PREFIX,
    build_upload_source_name,
    detect_tool_from_path,
    get_tool_upload_dir,
    is_valid_rag_tool,
    resolve_upload_source_path,
)
from config.settings import settings
from models.document import HistoryEntry, UploadBatchResult, VectorManagerPayload
from services.rag_service import clear_rag_corpus_cache
from services.vector_store_service import add_documents, embedding_backend_ready, get_collection, reset_vectorstore

SUPPORTED_TEXT_SUFFIXES = {".md", ".markdown", ".txt"}


def _iter_importable_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []

    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_TEXT_SUFFIXES
    )


def _normalize_tool_name(tool_name: Optional[str]) -> str:
    if is_valid_rag_tool(tool_name):
        return str(tool_name)
    return DEFAULT_RAG_TOOL


def _sanitize_filename(filename: Optional[str]) -> str:
    cleaned = Path(filename or "").name.strip()
    return cleaned


def _existing_uploaded_sources() -> set[str]:
    existing_sources = set()
    for item in get_uploaded_files():
        storage_path = item.get("storage_path")
        filename = item.get("filename")
        if storage_path:
            existing_sources.add(storage_path)
        elif filename:
            existing_sources.add(filename)
    return existing_sources


async def upload_markdown_files(
    files: list,
    tool_name: Optional[str] = None,
    client_start_time: Optional[float] = None,
    client_total_size: Optional[int] = None,
) -> dict:
    selected_tool = _normalize_tool_name(tool_name)
    upload_dir = get_tool_upload_dir(selected_tool)

    t0 = time.time()
    total_upload_size = 0
    success_files: list[str] = []
    updated_files: list[str] = []
    failed_files: list[str] = []
    indexed_files: list[str] = []
    warning_files: list[str] = []

    real_speed = None
    if client_start_time and client_total_size and client_start_time > 0:
        duration_from_client = t0 - (client_start_time / 1000.0)
        if duration_from_client > 0:
            real_speed = client_total_size / duration_from_client / 1024 / 1024
            print(
                f"UPLOAD TU CLIENT: {real_speed:.2f} MB/s "
                f"({client_total_size/1024/1024:.1f} MB trong {duration_from_client:.2f}s)"
            )

    existing_sources = _existing_uploaded_sources()

    for file in files:
        filename = _sanitize_filename(getattr(file, "filename", ""))
        if not filename:
            failed_files.append("file_khong_hop_le -> thieu ten file")
            continue

        if Path(filename).suffix.lower() not in SUPPORTED_TEXT_SUFFIXES:
            failed_files.append(f"{filename} -> chi ho tro .md/.markdown/.txt")
            continue

        source_name = build_upload_source_name(selected_tool, filename)
        file_path = upload_dir / filename
        existed_before = source_name in existing_sources or file_path.exists()

        try:
            t_read = time.time()
            content = await file.read()
            total_upload_size += len(content)
            text = content.decode("utf-8", errors="ignore")
            read_speed = len(content) / max(time.time() - t_read, 1e-6) / 1024 / 1024
            print(f"[DOC FILE] {filename}: {read_speed:.2f} MB/s ({len(content)/1024/1024:.2f} MB)")

            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)

            if existed_before:
                updated_files.append(filename)
            else:
                success_files.append(filename)

            add_uploaded_file(filename=filename, tool_name=selected_tool, storage_path=source_name)
            existing_sources.add(source_name)

            if not embedding_backend_ready():
                warning_files.append(f"{filename} -> da luu file nhung bo qua index vi embedding backend chua san sang")
            else:
                try:
                    t_chunk = time.time()
                    add_documents(
                        file_content=text,
                        filename=filename,
                        source_name=source_name,
                        tool_name=selected_tool,
                    )
                    indexed_files.append(filename)
                    chunk_speed = len(content) / max(time.time() - t_chunk, 1e-6) / 1024 / 1024
                    print(f"[CHUNK + ADD] {filename}: {chunk_speed:.2f} MB/s")
                except Exception as exc:
                    print(f"[INDEX WARNING] {filename}: {exc}")
                    warning_files.append(f"{filename} -> da luu file nhung chua index duoc: {exc}")
        except Exception as exc:
            print(f"[LOI] {filename}: {exc}")
            failed_files.append(f"{filename} -> loi: {exc}")

    clear_rag_corpus_cache()

    total_time = time.time() - t0
    avg_speed = total_upload_size / max(total_time, 1e-6) / 1024 / 1024
    print(
        f"HOAN TAT XU LY: {avg_speed:.2f} MB/s trung binh "
        f"({total_upload_size/1024/1024:.1f} MB trong {total_time:.2f}s)"
    )

    status = "success"
    if failed_files and (success_files or updated_files or warning_files):
        status = "partial"
    elif warning_files and not failed_files:
        status = "partial"
    elif failed_files and not success_files and not updated_files:
        status = "error"

    result = UploadBatchResult(
        status=status,
        added=len(success_files),
        updated=len(updated_files),
        failed=len(failed_files),
        indexed=len(indexed_files),
        warnings=len(warning_files),
        msg=(
            "<strong>HOAN TAT!</strong><br>"
            f"Nhom: {selected_tool} | Them: {len(success_files)} | "
            f"Cap nhat: {len(updated_files)} | Index: {len(indexed_files)} | "
            f"Canh bao: {len(warning_files)} | Loi: {len(failed_files)}"
        ),
        real_speed=f"{real_speed:.2f}" if real_speed else None,
        tool_name=selected_tool,
        detail={
            "added": success_files,
            "updated": updated_files,
            "failed": failed_files,
            "indexed": indexed_files,
            "warnings": warning_files,
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

    corpus_records = _iter_seed_source_records()
    if not corpus_records:
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

    for path, tool_name, source_name in corpus_records:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            add_documents(
                file_content=text,
                filename=path.name,
                source_name=source_name,
                tool_name=tool_name,
            )
            imported_files += 1
        except Exception as exc:
            print(f"[IMPORT QA CORPUS LOI] {source_name}: {exc}")
            failed_sources.append(source_name)

    clear_rag_corpus_cache()
    total_chunks = coll.count()
    status = "success" if imported_files > 0 and not failed_sources else "partial" if imported_files > 0 else "error"
    action = "Reset + import" if reset_first else "Import"
    msg = (
        f"{action} xong: {imported_files}/{len(corpus_records)} file tu qa_generated_fixed. "
        f"Vector store hien co {total_chunks} chunks."
    )
    if failed_sources:
        msg += f" Loi: {len(failed_sources)} file."

    return {
        "status": status,
        "msg": msg,
        "total_files": len(corpus_records),
        "imported_files": imported_files,
        "failed_files": len(failed_sources),
        "failed_sources": failed_sources[:20],
        "total_chunks": total_chunks,
    }


def delete_uploaded_document(source_name: str) -> None:
    source_name = str(source_name).replace("\\", "/")
    candidate_sources = [source_name]

    if "/" not in source_name:
        matched_sources = [
            item.get("storage_path", "")
            for item in get_uploaded_files()
            if item.get("filename") == source_name and item.get("storage_path")
        ]
        if matched_sources:
            candidate_sources = matched_sources

    for candidate in candidate_sources:
        resolve_upload_source_path(candidate).unlink(missing_ok=True)
        delete_uploaded_file(candidate)
        try:
            get_collection().delete(where={"source": candidate})
        except Exception as exc:
            print(f"Bo qua xoa vector cho {candidate}: {exc}")
    clear_rag_corpus_cache()


def reset_document_store() -> None:
    reset_vectorstore()
    if settings.UPLOAD_DIR.exists():
        shutil.rmtree(settings.UPLOAD_DIR)
    if settings.RAG_UPLOAD_ROOT.exists():
        shutil.rmtree(settings.RAG_UPLOAD_ROOT)
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    settings.RAG_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    clear_uploaded_files()
    clear_rag_corpus_cache()


def _infer_vector_tool_name(source: str, raw_tool_name: Optional[str]) -> Optional[str]:
    if is_valid_rag_tool(raw_tool_name):
        return str(raw_tool_name)

    normalized_source = str(source or "").replace("\\", "/")
    if not normalized_source or normalized_source == "BOT_RULE":
        return None

    path_parts = PurePosixPath(normalized_source).parts
    if len(path_parts) >= 3 and path_parts[0] == UPLOAD_SOURCE_PREFIX and is_valid_rag_tool(path_parts[1]):
        return path_parts[1]

    inferred_tool = detect_tool_from_path(settings.QA_CORPUS_ROOT / Path(normalized_source))
    if is_valid_rag_tool(inferred_tool):
        return str(inferred_tool)

    return DEFAULT_RAG_TOOL


def _display_vector_source(source: str) -> str:
    normalized_source = str(source or "").replace("\\", "/")
    if not normalized_source:
        return "unknown.md"

    if normalized_source == "BOT_RULE":
        return "BOT_RULE"

    return PurePosixPath(normalized_source).name or normalized_source


def _build_vector_tool_groups(chunks_by_file: dict[str, list[dict]], limit_per_file: int) -> list[dict]:
    grouped_sources: dict[str, dict[str, list[dict]]] = {tool_name: {} for tool_name in RAG_TOOL_ORDER}
    theme_by_tool = {
        "student_handbook_rag": "orange",
        "school_policy_rag": "purple",
        "student_faq_rag": "teal",
    }

    for source, chunks in chunks_by_file.items():
        if not chunks:
            continue

        tool_name = _infer_vector_tool_name(source, chunks[0].get("tool_name"))
        if not is_valid_rag_tool(tool_name):
            continue

        grouped_sources.setdefault(str(tool_name), {})[source] = chunks

    tool_groups: list[dict] = []
    for tool_name in RAG_TOOL_ORDER:
        file_items: list[dict] = []
        total_chunks = 0

        for source, items in sorted(grouped_sources.get(tool_name, {}).items(), key=lambda item: item[0]):
            sorted_items = sorted(items, key=lambda chunk: chunk["level"], reverse=True)
            is_upload_source = str(source).replace("\\", "/").startswith(f"{UPLOAD_SOURCE_PREFIX}/")
            total_chunks += len(sorted_items)

            file_items.append(
                {
                    "source": source,
                    "display_name": _display_vector_source(source),
                    "source_label": source,
                    "chunk_count": len(sorted_items),
                    "chunks": sorted_items[:limit_per_file],
                    "tool_name": tool_name,
                    "is_upload_source": is_upload_source,
                    "source_kind_label": "File upload" if is_upload_source else "Seed corpus",
                }
            )

        profile = RAG_TOOL_PROFILES[tool_name]
        tool_groups.append(
            {
                "name": tool_name,
                "label": str(profile.get("label", tool_name)),
                "description": str(profile.get("description", "")),
                "theme": theme_by_tool.get(tool_name, "teal"),
                "total_files": len(file_items),
                "total_chunks": total_chunks,
                "files": file_items,
            }
        )

    return tool_groups


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
                "word_count": meta.get("word_count", len(doc.split())),
                "tool_name": meta.get("tool_name", "unassigned"),
            }
        )

    tool_groups = _build_vector_tool_groups(dict(chunks_by_file), limit_per_file)
    visible_chunks_by_file = {
        file_item["source"]: file_item["chunks"]
        for group in tool_groups
        for file_item in group["files"]
    }
    total_chunks = sum(group["total_chunks"] for group in tool_groups)
    total_files = sum(group["total_files"] for group in tool_groups)

    payload = VectorManagerPayload(
        chunks_by_file=visible_chunks_by_file,
        total_chunks=total_chunks,
        total_files=total_files,
        tool_groups=tool_groups,
    )
    return payload.to_dict()


def _iter_seed_source_records() -> list[tuple[Path, str, str]]:
    records: list[tuple[Path, str, str]] = []
    root = settings.QA_CORPUS_ROOT
    if not root.exists():
        return records

    for path in _iter_importable_paths(root):
        try:
            source_name = path.relative_to(root).as_posix()
        except ValueError:
            source_name = path.name
        tool_name = detect_tool_from_path(path) or DEFAULT_RAG_TOOL
        records.append((path, tool_name, source_name))

    return records


def _iter_uploaded_source_records() -> list[tuple[Path, str, str]]:
    records: list[tuple[Path, str, str]] = []

    for tool_name in RAG_TOOL_ORDER:
        for path in _iter_importable_paths(get_tool_upload_dir(tool_name)):
            records.append((path, tool_name, build_upload_source_name(tool_name, path.name)))

    for path in _iter_importable_paths(settings.UPLOAD_DIR):
        records.append((path, DEFAULT_RAG_TOOL, path.name))

    return records


def reingest_uploaded_documents() -> tuple[int, int]:
    source_records: list[tuple[Path, str, str]] = []
    seen_sources: set[str] = set()

    for record in [*_iter_seed_source_records(), *_iter_uploaded_source_records()]:
        path, tool_name, source_name = record
        normalized_source = str(source_name).replace("\\", "/")
        if normalized_source in seen_sources:
            continue
        seen_sources.add(normalized_source)
        source_records.append((path, tool_name, normalized_source))

    if not source_records:
        return 0, 0

    reset_vectorstore()
    total_files = 0
    total_chunks = 0
    coll = get_collection()

    for path, tool_name, source_name in source_records:
        try:
            before_count = coll.count()
            text = path.read_text(encoding="utf-8", errors="ignore")
            add_documents(
                file_content=text,
                filename=path.name,
                source_name=source_name,
                tool_name=tool_name,
            )
            total_files += 1
            total_chunks += max(coll.count() - before_count, 0)
        except Exception as exc:
            print(f"Re-ingest loi {path.name}: {exc}")

    clear_rag_corpus_cache()
    return total_files, total_chunks


def get_history_page_data(page: int, per_page: int = 50) -> dict:
    offset = (page - 1) * per_page
    conn = sqlite3.connect(settings.DB_PATH)
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
