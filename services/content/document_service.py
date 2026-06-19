from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path
from typing import Callable, Optional

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
from models.document import UploadBatchResult, VectorManagerPayload
from pipelines.document_admin_pipeline import (
    build_vector_manager_summary,
    iter_seed_source_records as iter_seed_source_records_from_pipeline,
    iter_uploaded_source_records as iter_uploaded_source_records_from_pipeline,
    reingest_source_records,
)
from repositories.conversation_repository import get_chat_history_page
from repositories.config_repository import get_config, set_config
from repositories.upload_repository import (
    clear_uploaded_file_records,
    list_uploaded_files,
    record_uploaded_file,
    remove_uploaded_file,
)
from repositories.vector_repository import (
    delete_vector_source,
    get_vector_collection as get_collection,
    get_vector_collection_readonly,
)
from shared.vector_utils import display_vector_source, infer_vector_tool_name
from services.rag.rag_corpus import clear_rag_corpus_cache
from services.vector.vector_store_service import add_documents, embedding_backend_ready, reset_vectorstore
from services.content.upload_validation import (
    SUPPORTED_TEXT_SUFFIXES,
    UploadValidationError,
    validate_text_upload,
)

get_uploaded_files = list_uploaded_files
add_uploaded_file = record_uploaded_file

SEED_CORPUS_SIGNATURE_KEY = "seed_corpus_signature"
_VECTOR_MANAGER_PAYLOAD_CACHE: dict[int, dict] = {}


def _normalize_tool_name(tool_name: Optional[str]) -> str:
    if is_valid_rag_tool(tool_name):
        return str(tool_name)
    return DEFAULT_RAG_TOOL


def _sanitize_filename(filename: Optional[str]) -> str:
    cleaned = Path(filename or "").name.strip()
    return cleaned


def clear_vector_manager_cache() -> None:
    _VECTOR_MANAGER_PAYLOAD_CACHE.clear()


def _clear_knowledge_base_cache() -> None:
    try:
        from services.content.knowledge_base_service import clear_knowledge_base_cache

        clear_knowledge_base_cache()
    except Exception as exc:
        print(f"[CACHE WARNING] Failed to clear knowledge base cache: {exc}")


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


def _build_seed_corpus_signature(records: list[tuple[Path, str, str]]) -> str:
    digest = hashlib.sha256()
    for path, tool_name, source_name in sorted(records, key=lambda item: item[2]):
        digest.update(source_name.encode("utf-8", errors="ignore"))
        digest.update(b"\0")
        digest.update(tool_name.encode("utf-8", errors="ignore"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def compute_seed_corpus_signature(
    corpus_records: Optional[list[tuple[Path, str, str]]] = None,
) -> str:
    records = corpus_records if corpus_records is not None else _iter_seed_source_records()
    if not records:
        return ""
    return _build_seed_corpus_signature(records)


async def upload_markdown_files(
    files: list,
    tool_name: Optional[str] = None,
    client_start_time: Optional[float] = None,
    client_total_size: Optional[int] = None,
    progress_callback: Optional[Callable[[str, int], None]] = None,
) -> dict:
    selected_tool = _normalize_tool_name(tool_name)
    upload_dir = get_tool_upload_dir(selected_tool)
    file_list = list(files or [])

    if len(file_list) > settings.MAX_UPLOAD_FILES:
        return UploadBatchResult(
            status="error",
            failed=len(file_list),
            msg=(
                f"Too many files. Maximum is {settings.MAX_UPLOAD_FILES} files per upload batch."
            ),
            tool_name=selected_tool,
            detail={
                "added": [],
                "updated": [],
                "failed": [f"batch -> too many files ({len(file_list)}/{settings.MAX_UPLOAD_FILES})"],
                "indexed": [],
                "warnings": [],
            },
        ).to_dict()

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
    if progress_callback:
        progress_callback("validating", 10)

    for file in file_list:
        raw_filename = str(getattr(file, "filename", "") or "")
        display_filename = _sanitize_filename(raw_filename) or "invalid-upload"

        try:
            t_read = time.time()
            content = await file.read()
            if total_upload_size + len(content) > settings.MAX_UPLOAD_BATCH_SIZE_BYTES:
                failed_files.append(
                    f"{display_filename} -> upload batch too large; maximum is {settings.MAX_UPLOAD_BATCH_SIZE_BYTES // (1024 * 1024)}MB"
                )
                continue
            validated = validate_text_upload(
                filename=raw_filename,
                content=content,
                content_type=str(getattr(file, "content_type", "") or ""),
                max_size_bytes=settings.MAX_UPLOAD_FILE_SIZE_BYTES,
            )
            filename = validated.filename
            text = validated.text
            source_name = build_upload_source_name(selected_tool, filename)
            file_path = upload_dir / filename
            existed_before = source_name in existing_sources or file_path.exists()
            total_upload_size += len(content)
            if progress_callback:
                progress_callback("extracting", 25)
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
                warning_files.append(f"{filename} -> saved but skipped indexing because embedding backend is not ready")
            else:
                try:
                    t_chunk = time.time()
                    if progress_callback:
                        progress_callback("chunking", 45)
                        progress_callback("embedding", 65)
                    add_documents(
                        file_content=text,
                        filename=filename,
                        source_name=source_name,
                        tool_name=selected_tool,
                    )
                    if progress_callback:
                        progress_callback("indexing", 85)
                    indexed_files.append(filename)
                    chunk_speed = len(content) / max(time.time() - t_chunk, 1e-6) / 1024 / 1024
                    print(f"[CHUNK + ADD] {filename}: {chunk_speed:.2f} MB/s")
                except Exception as exc:
                    print(f"[INDEX WARNING] {filename}: {exc}")
                    warning_files.append(f"{filename} -> saved but indexing failed: {exc}")
        except UploadValidationError as exc:
            failed_files.append(f"{display_filename} -> {exc}")
        except Exception as exc:
            print(f"[ERROR] {display_filename}: {exc}")
            failed_files.append(f"{display_filename} -> error: {exc}")

    clear_rag_corpus_cache()
    clear_vector_manager_cache()
    _clear_knowledge_base_cache()

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
            "<strong>DONE!</strong><br>"
            f"Tool: {selected_tool} | Added: {len(success_files)} | "
            f"Updated: {len(updated_files)} | Indexed: {len(indexed_files)} | "
            f"Warnings: {len(warning_files)} | Failed: {len(failed_files)}"
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
            "msg": f"Corpus directory not found: {root}",
            "total_files": 0,
            "imported_files": 0,
            "failed_files": 0,
            "total_chunks": get_collection().count(),
        }

    corpus_records = _iter_seed_source_records()
    if not corpus_records:
        return {
            "status": "error",
            "msg": f"Directory {root} has no .md/.txt files to import",
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
    clear_vector_manager_cache()
    _clear_knowledge_base_cache()
    total_chunks = get_collection().count()
    status = "success" if imported_files > 0 and not failed_sources else "partial" if imported_files > 0 else "error"
    action = "Reset + import" if reset_first else "Import"
    msg = (
        f"{action} xong: {imported_files}/{len(corpus_records)} file tu seed corpus chinh. "
        f"Vector store hien co {total_chunks} chunks."
    )
    if failed_sources:
        msg += f" Failed: {len(failed_sources)} file."

    if imported_files > 0 and not failed_sources:
        try:
            set_config(SEED_CORPUS_SIGNATURE_KEY, compute_seed_corpus_signature(corpus_records))
        except Exception as exc:
            print(f"[SEED CORPUS SIGNATURE WARNING] {exc}")

    return {
        "status": status,
        "msg": msg,
        "total_files": len(corpus_records),
        "imported_files": imported_files,
        "failed_files": len(failed_sources),
        "failed_sources": failed_sources[:20],
        "total_chunks": total_chunks,
    }


def sync_seed_corpus_index(reset_first: bool = False) -> dict:
    corpus_records = _iter_seed_source_records()
    if not corpus_records:
        return {
            "status": "error",
            "msg": f"Directory {settings.QA_CORPUS_ROOT} has no .md/.txt files to import",
            "total_files": 0,
            "imported_files": 0,
            "failed_files": 0,
            "total_chunks": get_vector_collection_readonly().count(),
        }

    current_signature = compute_seed_corpus_signature(corpus_records)
    stored_signature = get_config(SEED_CORPUS_SIGNATURE_KEY, "")
    collection = get_vector_collection_readonly()
    total_chunks = collection.count()

    if stored_signature == current_signature and total_chunks > 0:
        return {
            "status": "skipped",
            "msg": "Seed corpus already synchronized.",
            "total_files": len(corpus_records),
            "imported_files": 0,
            "failed_files": 0,
            "total_chunks": total_chunks,
            "stored_signature": stored_signature,
            "current_signature": current_signature,
        }

    result = import_seed_corpus(reset_first=reset_first)
    result["stored_signature"] = stored_signature
    result["current_signature"] = current_signature
    if result.get("failed_files", 0) == 0 and result.get("imported_files", 0) > 0:
        try:
            set_config(SEED_CORPUS_SIGNATURE_KEY, current_signature)
        except Exception as exc:
            print(f"[SEED CORPUS SIGNATURE WARNING] {exc}")
        result["seed_corpus_signature"] = current_signature
    return result


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
            print(f"Skip vector delete for {candidate}: {exc}")
    clear_rag_corpus_cache()
    clear_vector_manager_cache()
    _clear_knowledge_base_cache()


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
    clear_vector_manager_cache()
    _clear_knowledge_base_cache()


def get_vector_manager_payload(limit_per_file: int = 50) -> dict:
    normalized_limit = max(1, int(limit_per_file or 0))
    cached_payload = _VECTOR_MANAGER_PAYLOAD_CACHE.get(normalized_limit)
    if cached_payload is not None:
        return cached_payload

    data = get_vector_collection_readonly().get(include=["metadatas", "documents"])
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
    result = payload.to_dict()
    _VECTOR_MANAGER_PAYLOAD_CACHE[normalized_limit] = result
    return result


def _iter_seed_source_records() -> list[tuple[Path, str, str]]:
    return iter_seed_source_records_from_pipeline(
        settings.QA_CORPUS_ROOT,
        default_tool=None,
        detect_tool_from_path=detect_tool_from_path,
        supported_suffixes=SUPPORTED_TEXT_SUFFIXES,
    )


def _iter_uploaded_source_records() -> list[tuple[Path, str, str]]:
    return iter_uploaded_source_records_from_pipeline(
        rag_tool_order=RAG_TOOL_ORDER,
        get_tool_upload_dir=get_tool_upload_dir,
        build_upload_source_name=build_upload_source_name,
        upload_dir=settings.UPLOAD_DIR,
        default_tool=DEFAULT_RAG_TOOL,
        supported_suffixes=SUPPORTED_TEXT_SUFFIXES,
    )


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
    result = reingest_source_records(
        source_records,
        reset_vectorstore=reset_vectorstore,
        get_collection=get_collection,
        add_documents=add_documents,
        clear_rag_corpus_cache=clear_rag_corpus_cache,
    )
    clear_vector_manager_cache()
    _clear_knowledge_base_cache()
    return result


def get_history_page_data(
    page: int,
    per_page: int = 50,
    owner_username: str | None = None,
    include_uploaded_files: bool = True,
    include_legacy_unowned: bool = False,
) -> dict:
    payload = get_chat_history_page(
        page=page,
        per_page=per_page,
        owner_username=owner_username,
        include_legacy_unowned=include_legacy_unowned,
    )
    payload["uploaded_files"] = get_uploaded_files() if include_uploaded_files else []
    return payload
