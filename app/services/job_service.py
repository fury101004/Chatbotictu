"""In-memory background job tracking helpers."""

from __future__ import annotations

import threading
import traceback
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


JobTarget = Callable[[str, Callable[..., None]], Dict[str, Any]]

_JOB_LOCK = threading.RLock()
_JOBS: Dict[str, Dict[str, Any]] = {}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _copy_job(job: Dict[str, Any]) -> Dict[str, Any]:
    copied = dict(job)
    copied["payload"] = dict(job.get("payload") or {})
    return copied


def update_job(
    job_id: str,
    *,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    stage: Optional[str] = None,
    detail: Optional[str] = None,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    started_at: Optional[str] = None,
    finished_at: Optional[str] = None,
) -> Dict[str, Any]:
    with _JOB_LOCK:
        if job_id not in _JOBS:
            raise KeyError(f"Unknown job id: {job_id}")

        job = _JOBS[job_id]
        if status is not None:
            job["status"] = status
        if progress is not None:
            job["progress"] = max(0, min(int(progress), 100))
        if stage is not None:
            job["stage"] = stage
        if detail is not None:
            job["detail"] = detail
        if result is not None:
            job["result"] = result
        if error is not None:
            job["error"] = error
        if started_at is not None:
            job["started_at"] = started_at
        if finished_at is not None:
            job["finished_at"] = finished_at

        job["updated_at"] = _now()
        return _copy_job(job)


def create_job(kind: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    job_id = str(uuid.uuid4())
    job = {
        "id": job_id,
        "kind": kind,
        "status": "queued",
        "progress": 0,
        "stage": "queued",
        "detail": "",
        "payload": dict(payload or {}),
        "result": None,
        "error": None,
        "created_at": _now(),
        "updated_at": _now(),
        "started_at": None,
        "finished_at": None,
    }
    with _JOB_LOCK:
        _JOBS[job_id] = job
    return _copy_job(job)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _JOB_LOCK:
        job = _JOBS.get(job_id)
        return _copy_job(job) if job is not None else None


def list_jobs(*, kind: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    with _JOB_LOCK:
        jobs = [_copy_job(job) for job in _JOBS.values()]

    if kind is not None:
        jobs = [job for job in jobs if job["kind"] == kind]

    jobs.sort(key=lambda item: item["created_at"], reverse=True)
    return jobs[:limit]


def get_active_job(*, kinds: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    active_statuses = {"queued", "running"}
    candidates = list_jobs(limit=100)
    for job in candidates:
        if kinds is not None and job["kind"] not in kinds:
            continue
        if job["status"] in active_statuses:
            return job
    return None


def start_background_job(kind: str, target: JobTarget, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    job = create_job(kind, payload=payload)
    job_id = job["id"]

    def progress_callback(
        *,
        progress: Optional[int] = None,
        stage: Optional[str] = None,
        detail: Optional[str] = None,
        status: Optional[str] = None,
    ) -> None:
        update_job(
            job_id,
            status=status,
            progress=progress,
            stage=stage,
            detail=detail,
        )

    def runner() -> None:
        update_job(
            job_id,
            status="running",
            progress=1,
            stage="starting",
            started_at=_now(),
        )
        try:
            result = target(job_id, progress_callback)
        except Exception as exc:  # pragma: no cover - defensive runtime path
            update_job(
                job_id,
                status="failed",
                progress=100,
                stage="failed",
                detail=traceback.format_exc(limit=5),
                error=str(exc) or exc.__class__.__name__,
                finished_at=_now(),
            )
            return

        update_job(
            job_id,
            status="completed",
            progress=100,
            stage="completed",
            result=result,
            finished_at=_now(),
        )

    thread = threading.Thread(target=runner, name=f"job-{kind}-{job_id[:8]}", daemon=True)
    thread.start()
    return get_job(job_id) or job
