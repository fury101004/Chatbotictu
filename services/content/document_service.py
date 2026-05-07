from __future__ import annotations

import shutil
import time
from pathlib import Path, PurePosixPath
from typing import Optional

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
from pipelines.document_admin_pipeline import (
    build_vector_manager_summary,
    build_vector_tool_groups,
    iter_importable_paths as iter_importable_paths_from_pipeline,
    iter_seed_source_records as iter_seed_source_records_from_pipeline,
    iter_uploaded_source_records as iter_uploaded_source_records_from_pipeline,
    reingest_source_records,
)
from repositories.conversation_repository import get_chat_history_page
from repositories.upload_repository import (
    clear_uploaded_file_records,
    list_uploaded_files,
    record_uploaded_file,
    remove_uploaded_file,
)
from repositories.vector_repository import (
    delete_vector_source,
    get_vector_collection as get_collection,
)
from shared.vector_utils import display_vector_source, infer_vector_tool_name
from services.rag.rag_corpus import clear_rag_corpus_cache
from services.vector.vector_store_service import add_documents, embedding_backend_ready, reset_vectorstore

SUPPORTED_TEXT_SUFFIXES = {".md", ".markdown", ".txt"}
get_uploaded_files = list_uploaded_files
add_uploaded_file = record_uploaded_file


def _iter_importable_paths(root: Path) -> list[Path]:
    return iter_importable_paths_from_pipeline(root, supported_suffixes=SUPPORTED_TEXT_SUFFIXES)


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
                warning_files.append(f"{filename} -> đã lưu file nhưng bỏ qua index vì embedding backend chưa sẵn sàng")
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
                    warning_files.append(f"{filename} -> đã lưu file nhưng chưa index được: {exc}")
        except Exception as exc:
            print(f"[LỖI] {filename}: {exc}")
            failed_files.append(f"{filename} -> lỗi: {exc}")

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
            "<strong>HOÀN TẤT!</strong><br>"
            f"Nhóm: {selected_tool} | Thêm: {len(success_files)} | "
            f"Cập nhật: {len(updated_files)} | Index: {len(indexed_files)} | "
            f"Cảnh báo: {len(warning_files)} | Lỗi: {len(failed_files)}"
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
            "msg": f"Không tìm thấy thư mục corpus: {root}",
            "total_files": 0,
            "imported_files": 0,
            "failed_files": 0,
            "total_chunks": get_collection().count(),
        }

    corpus_records = _iter_seed_source_records()
    if not corpus_records:
        return {
            "status": "error",
            "msg": f"Thư mục {root} chưa có file .md/.txt để import",
            "total_files": 0,
            "imported_files": 0,
            "failed_files": 0,
            "total_chunks": get_collection().count(),
        }

    if reset_first:
        reset_vectorstore()

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
    total_chunks = get_collection().count()
    status = "success" if imported_files > 0 and not failed_sources else "partial" if imported_files > 0 else "error"
    action = "Reset + import" if reset_first else "Import"
    msg = (
        f"{action} xong: {imported_files}/{len(corpus_records)} file tu seed corpus chinh. "
        f"Vector store hien co {total_chunks} chunks."
    )
    if failed_sources:
        msg += f" Lỗi: {len(failed_sources)} file."

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
        remove_uploaded_file(candidate)
        try:
            delete_vector_source(candidate)
        except Exception as exc:
            print(f"Bỏ qua xóa vector cho {candidate}: {exc}")
    clear_rag_corpus_cache()


def reset_document_store() -> None:
    reset_vectorstore()
    if settings.UPLOAD_DIR.exists():
        shutil.rmtree(settings.UPLOAD_DIR)
    if settings.RAG_UPLOAD_ROOT.exists():
        shutil.rmtree(settings.RAG_UPLOAD_ROOT)
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    settings.RAG_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    clear_uploaded_file_records()
    clear_rag_corpus_cache()


def _build_vector_tool_groups(chunks_by_file: dict[str, list[dict]], limit_per_file: int) -> list[dict]:
    return build_vector_tool_groups(
        chunks_by_file,
        rag_tool_order=RAG_TOOL_ORDER,
        rag_tool_profiles=RAG_TOOL_PROFILES,
        infer_vector_tool_name=infer_vector_tool_name,
        is_valid_rag_tool=is_valid_rag_tool,
        display_vector_source=display_vector_source,
        upload_source_prefix=UPLOAD_SOURCE_PREFIX,
        limit_per_file=limit_per_file,
    )


def get_vector_manager_payload(limit_per_file: int = 50) -> dict:
    data = get_collection().get(include=["metadatas", "documents"])
    summary = build_vector_manager_summary(
        data,
        rag_tool_order=RAG_TOOL_ORDER,
        rag_tool_profiles=RAG_TOOL_PROFILES,
        infer_vector_tool_name=infer_vector_tool_name,
        is_valid_rag_tool=is_valid_rag_tool,
        display_vector_source=display_vector_source,
        upload_source_prefix=UPLOAD_SOURCE_PREFIX,
        limit_per_file=limit_per_file,
    )
    payload = VectorManagerPayload(
        chunks_by_file=summary["chunks_by_file"],
        total_chunks=summary["total_chunks"],
        total_files=summary["total_files"],
        tool_groups=summary["tool_groups"],
    )
    return payload.to_dict()

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
                "title": meta.get("title", "Không có tiêu đề"),
                "level": meta.get("level", 1),
                "word_count": meta.get("word_count", len(doc.split())),
                "tool_name": meta.get("tool_name", "unassigned"),
                "academic_year": meta.get("academic_year", ""),
                "chapter": meta.get("chapter", ""),
                "section": meta.get("section", ""),
                "page_number": meta.get("page_number", -1),
                "document_type": meta.get("document_type", ""),
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
    return iter_seed_source_records_from_pipeline(
        settings.QA_CORPUS_ROOT,
        default_tool=DEFAULT_RAG_TOOL,
        detect_tool_from_path=detect_tool_from_path,
        supported_suffixes=SUPPORTED_TEXT_SUFFIXES,
    )
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
    return iter_uploaded_source_records_from_pipeline(
        rag_tool_order=RAG_TOOL_ORDER,
        get_tool_upload_dir=get_tool_upload_dir,
        build_upload_source_name=build_upload_source_name,
        upload_dir=settings.UPLOAD_DIR,
        default_tool=DEFAULT_RAG_TOOL,
        supported_suffixes=SUPPORTED_TEXT_SUFFIXES,
    )
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
    return reingest_source_records(
        source_records,
        reset_vectorstore=reset_vectorstore,
        get_collection=get_collection,
        add_documents=add_documents,
        clear_rag_corpus_cache=clear_rag_corpus_cache,
    )


def get_history_page_data(page: int, per_page: int = 50) -> dict:
    payload = get_chat_history_page(page=page, per_page=per_page)
    payload["uploaded_files"] = get_uploaded_files()
    return payload

