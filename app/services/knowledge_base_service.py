"""Knowledge-base upload, rebuild, job, and vector-store helpers."""

from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence

from fastapi import UploadFile

from app.core.config import (
    ACTIVE_LLM_MODEL,
    ACTIVE_LLM_PROVIDER,
    CLEAN_MD_DIR,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    MAX_UPLOAD_SIZE_MB,
    RAG_MD_DIR,
    RAW_DATA_DIR,
    ROOT_DIR,
    TXT_DATA_DIR,
    UPLOADS_DIR_NAME,
    VECTOR_DB_DIR,
)
from app.services.job_service import get_active_job, get_job, list_jobs, start_background_job


ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".md"}
ALLOWED_UPLOAD_FORMAT_LABEL = "PDF, DOCX hoặc Markdown (.md)"
ALLOWED_UPLOAD_ROUTES = ("policy", "handbook")
KNOWLEDGE_JOB_KINDS = ["knowledge_upload", "knowledge_rebuild"]
ROUTES = ("handbook", "policy", "faq")
ROUTE_LABELS = {
    "handbook": "Agent Sổ tay sinh viên",
    "policy": "Agent Chính sách - Công văn - Quyết định",
    "faq": "Agent Câu hỏi sinh viên thường dùng",
}
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
_PIPELINE_LOCK = threading.Lock()


def _upload_root() -> Path:
    return Path(RAW_DATA_DIR) / UPLOADS_DIR_NAME


def _runtime_job_root() -> Path:
    try:
        common_root = Path(
            os.path.commonpath(
                [
                    str(CLEAN_MD_DIR.resolve()),
                    str(RAG_MD_DIR.resolve()),
                    str(TXT_DATA_DIR.resolve()),
                    str(VECTOR_DB_DIR.resolve()),
                ]
            )
        )
    except ValueError:
        common_root = ROOT_DIR

    return common_root / ".knowledge_jobs"


def _load_pipeline_runtime() -> Dict[str, Any]:
    try:
        import app.data.clean_raw as clean_raw_module
        import app.data.pipeline as pipeline_module
        import prepare_rag_md as prepare_rag_module
        from app.data.clean_raw import build_clean_markdown
        from app.data.pipeline import (
            build_multi_vector_db,
            invalidate_vector_runtime_cache,
            prepare_agent_corpora,
        )
        from prepare_rag_md import build_rag_markdown
    except (ModuleNotFoundError, ImportError) as exc:
        raise RuntimeError(
            f"Knowledge pipeline chưa sẵn sàng vì thiếu dependency: {getattr(exc, 'name', None) or exc.__class__.__name__}."
        ) from exc

    return {
        "clean_raw_module": clean_raw_module,
        "pipeline_module": pipeline_module,
        "prepare_rag_module": prepare_rag_module,
        "build_clean_markdown": build_clean_markdown,
        "build_multi_vector_db": build_multi_vector_db,
        "invalidate_vector_runtime_cache": invalidate_vector_runtime_cache,
        "prepare_agent_corpora": prepare_agent_corpora,
        "build_rag_markdown": build_rag_markdown,
    }


def _timestamp_for_path(path: Path) -> str:
    if not path.exists():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _normalize_upload_route(route: str | None) -> str:
    normalized = (route or "policy").strip().lower()
    if normalized not in ALLOWED_UPLOAD_ROUTES:
        raise ValueError("Route upload phải là policy hoặc handbook.")
    return normalized


def _validated_uploads(files: Sequence[UploadFile]) -> List[UploadFile]:
    valid_files = [file for file in files if file and str(file.filename or "").strip()]
    if not valid_files:
        raise ValueError("Bạn chưa chọn file để upload.")

    for file in valid_files:
        filename = Path(str(file.filename)).name
        extension = Path(filename).suffix.lower()
        if extension not in ALLOWED_UPLOAD_EXTENSIONS:
            raise ValueError(f"Chỉ hỗ trợ file {ALLOWED_UPLOAD_FORMAT_LABEL}.")

    return valid_files


def _build_destination_path(route: str, original_filename: str) -> Path:
    upload_dir = _upload_root() / route
    upload_dir.mkdir(parents=True, exist_ok=True)

    source_name = Path(original_filename).name or "upload"
    safe_stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in Path(source_name).stem)
    safe_stem = safe_stem.strip("_") or "upload"
    suffix = Path(source_name).suffix.lower()
    unique_name = f"{safe_stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{suffix}"
    return upload_dir / unique_name


def _save_upload(destination: Path, upload: UploadFile) -> None:
    size = 0
    upload.file.seek(0)
    try:
        with destination.open("wb") as output:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_SIZE_BYTES:
                    output.close()
                    destination.unlink(missing_ok=True)
                    raise ValueError(f"Mỗi file chỉ được tối đa {MAX_UPLOAD_SIZE_MB} MB.")
                output.write(chunk)
    finally:
        upload.file.seek(0)
        upload.file.close()


def _save_files(route: str, files: Sequence[UploadFile]) -> List[Path]:
    saved_paths: List[Path] = []
    for file in files:
        destination = _build_destination_path(route, str(file.filename or "upload"))
        _save_upload(destination, file)
        saved_paths.append(destination)
    return saved_paths


def _remove_paths(paths: Sequence[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            continue


def _copy_tree_if_exists(source: Path, destination: Path) -> None:
    if source.exists():
        shutil.copytree(source, destination, dirs_exist_ok=True)


def _stage_paths(job_id: str) -> Dict[str, Path]:
    stage_root = _runtime_job_root() / job_id
    return {
        "root": stage_root,
        "clean": stage_root / "clean_md",
        "rag": stage_root / "rag_md",
        "data": stage_root / "data",
        "vector": stage_root / "vector_db",
        "backups": stage_root / "_backups",
    }


def _prepare_stage_workspace(job_id: str, route: str) -> Dict[str, Path]:
    paths = _stage_paths(job_id)
    paths["root"].mkdir(parents=True, exist_ok=True)

    if route != "all":
        _copy_tree_if_exists(CLEAN_MD_DIR, paths["clean"])
        _copy_tree_if_exists(RAG_MD_DIR, paths["rag"])

    return paths


@contextmanager
def _patched_pipeline_dirs(
    stage_clean: Path,
    stage_rag: Path,
    stage_data: Path,
    stage_vector: Path,
    runtime: Dict[str, Any],
):
    clean_raw_module = runtime["clean_raw_module"]
    prepare_rag_module = runtime["prepare_rag_module"]
    pipeline_module = runtime["pipeline_module"]

    originals = {
        "clean_raw_clean": clean_raw_module.CLEAN_MD_DIR,
        "prepare_clean": prepare_rag_module.CLEAN_MD_DIR,
        "prepare_rag": prepare_rag_module.RAG_MD_DIR,
        "pipeline_rag": pipeline_module.RAG_MD_DIR,
        "pipeline_data": pipeline_module.TXT_DATA_DIR,
        "pipeline_vector": pipeline_module.VECTOR_DB_DIR,
    }

    clean_raw_module.CLEAN_MD_DIR = stage_clean
    prepare_rag_module.CLEAN_MD_DIR = stage_clean
    prepare_rag_module.RAG_MD_DIR = stage_rag
    pipeline_module.RAG_MD_DIR = stage_rag
    pipeline_module.TXT_DATA_DIR = stage_data
    pipeline_module.VECTOR_DB_DIR = stage_vector

    try:
        yield
    finally:
        clean_raw_module.CLEAN_MD_DIR = originals["clean_raw_clean"]
        prepare_rag_module.CLEAN_MD_DIR = originals["prepare_clean"]
        prepare_rag_module.RAG_MD_DIR = originals["prepare_rag"]
        pipeline_module.RAG_MD_DIR = originals["pipeline_rag"]
        pipeline_module.TXT_DATA_DIR = originals["pipeline_data"]
        pipeline_module.VECTOR_DB_DIR = originals["pipeline_vector"]


def _publish_directory(stage_path: Path, live_path: Path, backup_root: Path) -> Path | None:
    backup_path = backup_root / live_path.name
    if backup_path.exists():
        shutil.rmtree(backup_path)

    if live_path.exists():
        live_path.replace(backup_path)
    else:
        backup_path = None

    stage_path.replace(live_path)
    return backup_path


def _publish_staged_artifacts(stage_paths: Dict[str, Path]) -> None:
    mapping = [
        (stage_paths["clean"], CLEAN_MD_DIR),
        (stage_paths["rag"], RAG_MD_DIR),
        (stage_paths["data"], TXT_DATA_DIR),
        (stage_paths["vector"], VECTOR_DB_DIR),
    ]
    backup_root = stage_paths["backups"]
    backup_root.mkdir(parents=True, exist_ok=True)
    completed: List[tuple[Path, Path | None]] = []

    try:
        for stage_path, live_path in mapping:
            if not stage_path.exists():
                stage_path.mkdir(parents=True, exist_ok=True)
            backup_path = _publish_directory(stage_path, live_path, backup_root)
            completed.append((live_path, backup_path))
    except Exception:
        for live_path, backup_path in reversed(completed):
            if live_path.exists():
                shutil.rmtree(live_path)
            if backup_path is not None and backup_path.exists():
                backup_path.replace(live_path)
        raise

    for _live_path, backup_path in completed:
        if backup_path is not None and backup_path.exists():
            shutil.rmtree(backup_path)


def _relative_upload_paths(paths: Sequence[Path]) -> List[str]:
    return [str(path.relative_to(RAW_DATA_DIR)).replace("\\", "/") for path in paths]


def _run_pipeline_sync(
    job_id: str,
    route: str,
    saved_paths: Sequence[Path],
    progress: Callable[..., None],
) -> Dict[str, Any]:
    runtime = _load_pipeline_runtime()

    with _PIPELINE_LOCK:
        progress(progress=5, stage="preparing", detail="Đang chuẩn bị staging workspace.")
        stage_paths = _prepare_stage_workspace(job_id, route)

        try:
            with _patched_pipeline_dirs(
                stage_paths["clean"],
                stage_paths["rag"],
                stage_paths["data"],
                stage_paths["vector"],
                runtime,
            ):
                progress(progress=20, stage="clean_markdown", detail="Đang tạo clean markdown.")
                clean_stats = runtime["build_clean_markdown"](route=route, ocr_mode="auto")

                progress(progress=40, stage="rag_markdown", detail="Đang tối ưu markdown cho RAG.")
                rag_report = runtime["build_rag_markdown"](route=route)

                progress(progress=60, stage="corpora", detail="Đang chuẩn bị corpora cho các route.")
                corpus_counts = runtime["prepare_agent_corpora"]()

                progress(progress=80, stage="vector_build", detail="Đang build vector store.")
                vector_counts = runtime["build_multi_vector_db"](invalidate_cache=False)

            progress(progress=92, stage="publishing", detail="Đang publish dữ liệu staging sang live.")
            _publish_staged_artifacts(stage_paths)
            runtime["invalidate_vector_runtime_cache"]()
            status = get_vector_status()
        except Exception:
            if saved_paths:
                _remove_paths(saved_paths)
            raise
        finally:
            shutil.rmtree(stage_paths["root"], ignore_errors=True)

    progress(progress=100, stage="completed", detail="Đồng bộ kho tri thức thành công.")
    return {
        "message": (
            "Upload thành công và đã cập nhật vector store."
            if saved_paths
            else "Đã rebuild kho dữ liệu và vector store."
        ),
        "saved_files": _relative_upload_paths(saved_paths),
        "sync": {
            "route": route,
            "clean_stats": clean_stats,
            "rag_report": rag_report,
            "corpus_counts": corpus_counts,
            "vector_counts": vector_counts,
        },
        "status": status,
    }


def _ensure_no_active_knowledge_job() -> None:
    active_job = get_active_job(kinds=KNOWLEDGE_JOB_KINDS)
    if active_job is not None:
        raise ValueError("Đang có một job upload/rebuild khác chạy. Hãy đợi job hiện tại hoàn tất.")


def list_uploaded_sources(limit: int = 20) -> List[Dict[str, Any]]:
    upload_root = _upload_root()
    if not upload_root.exists():
        return []

    candidates = [
        path
        for path in upload_root.rglob("*")
        if path.is_file() and path.suffix.lower() in ALLOWED_UPLOAD_EXTENSIONS
    ]
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)

    uploads: List[Dict[str, Any]] = []
    for path in candidates[:limit]:
        try:
            relative_path = path.relative_to(RAW_DATA_DIR)
        except ValueError:
            relative_path = path

        uploads.append(
            {
                "filename": path.name,
                "route": path.parent.name.lower(),
                "relative_path": str(relative_path).replace("\\", "/"),
                "size_bytes": path.stat().st_size,
                "updated_at": _timestamp_for_path(path),
            }
        )

    return uploads


def list_knowledge_jobs(limit: int = 10) -> List[Dict[str, Any]]:
    jobs = list_jobs(limit=50)
    filtered = [job for job in jobs if job["kind"] in KNOWLEDGE_JOB_KINDS]
    return filtered[:limit]


def get_knowledge_job(job_id: str) -> Dict[str, Any] | None:
    job = get_job(job_id)
    if job is None or job["kind"] not in KNOWLEDGE_JOB_KINDS:
        return None
    return job


def get_vector_status() -> Dict[str, Any]:
    manifest = _load_json(Path(TXT_DATA_DIR) / "manifest.json")
    clean_reports = {
        route: _load_json(Path(CLEAN_MD_DIR) / "_reports" / f"{route}_source_report.json")
        for route in ("all", "policy", "handbook")
    }
    rag_reports = {
        route: _load_json(Path(RAG_MD_DIR) / "_reports" / f"{route}_rag_report.json")
        for route in ("all", "policy", "handbook")
    }

    routes: List[Dict[str, Any]] = []
    for route in ROUTES:
        store_dir = Path(VECTOR_DB_DIR) / route
        index_path = store_dir / "index.faiss"
        routes.append(
            {
                "route": route,
                "label": ROUTE_LABELS.get(route, route),
                "vector_path": str(store_dir),
                "vector_ready": index_path.exists(),
                "vector_updated_at": _timestamp_for_path(index_path if index_path.exists() else store_dir),
                "document_count": int((manifest.get("counts") or {}).get(route, 0)),
            }
        )

    active_job = get_active_job(kinds=KNOWLEDGE_JOB_KINDS)
    return {
        "pipeline_busy": _PIPELINE_LOCK.locked() or active_job is not None,
        "raw_data_dir": str(RAW_DATA_DIR),
        "upload_root": str(_upload_root()),
        "vector_root": str(VECTOR_DB_DIR),
        "max_upload_size_mb": MAX_UPLOAD_SIZE_MB,
        "routes": routes,
        "uploads": list_uploaded_sources(),
        "reports": {
            "clean": clean_reports,
            "rag": rag_reports,
            "manifest": manifest,
        },
        "llm": {
            "provider": ACTIVE_LLM_PROVIDER,
            "active_model": ACTIVE_LLM_MODEL,
            "gemini_configured": bool(GEMINI_API_KEY),
            "gemini_model": GEMINI_MODEL,
        },
        "jobs": {
            "active": active_job,
            "recent": list_knowledge_jobs(),
        },
    }


def start_upload_job(files: Sequence[UploadFile], route: str) -> Dict[str, Any]:
    normalized_route = _normalize_upload_route(route)
    valid_files = _validated_uploads(files)
    _load_pipeline_runtime()
    _ensure_no_active_knowledge_job()

    saved_paths = _save_files(normalized_route, valid_files)
    payload = {
        "route": normalized_route,
        "saved_files": _relative_upload_paths(saved_paths),
    }

    try:
        return start_background_job(
            "knowledge_upload",
            lambda job_id, progress: _run_pipeline_sync(job_id, normalized_route, saved_paths, progress),
            payload=payload,
        )
    except Exception:
        _remove_paths(saved_paths)
        raise


def start_rebuild_job() -> Dict[str, Any]:
    _load_pipeline_runtime()
    _ensure_no_active_knowledge_job()
    return start_background_job(
        "knowledge_rebuild",
        lambda job_id, progress: _run_pipeline_sync(job_id, "all", [], progress),
        payload={"route": "all"},
    )
