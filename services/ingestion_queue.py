from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Awaitable, Callable

from fastapi import BackgroundTasks

from config.settings import settings
from repositories.ingestion_repository import IngestionJobRepository, TERMINAL_INGESTION_STATUSES


@dataclass(slots=True)
class QueuedUploadFile:
    filename: str
    content: bytes
    content_type: str = ""

    async def read(self) -> bytes:
        return self.content


class IngestionQueue:
    def __init__(self, *, ttl_seconds: int = 3600, db_path: str | None = None) -> None:
        self.ttl_seconds = ttl_seconds
        self._repository = IngestionJobRepository(db_path)

    async def enqueue_upload(
        self,
        *,
        files: list[Any],
        tool_name: str,
        processor: Callable[..., Awaitable[dict]],
        background_tasks: BackgroundTasks,
        client_start_time: float | None = None,
        client_total_size: int | None = None,
    ) -> dict[str, Any]:
        self.cleanup()
        job_id = str(uuid.uuid4())
        snapshots: list[QueuedUploadFile] = []
        total_size = 0

        for upload in files:
            content = await upload.read()
            total_size += len(content)
            snapshots.append(
                QueuedUploadFile(
                    filename=str(getattr(upload, "filename", "") or "upload.txt"),
                    content=content,
                    content_type=str(getattr(upload, "content_type", "") or ""),
                )
            )

        now = time.time()
        job = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0,
            "error": None,
            "result": None,
            "tool_name": tool_name,
            "file_count": len(snapshots),
            "total_size": total_size,
            "created_at": now,
            "updated_at": now,
        }
        self._repository.create(job)
        background_tasks.add_task(
            self._run_upload_job,
            job_id,
            snapshots,
            tool_name,
            processor,
            client_start_time,
            client_total_size,
        )
        return self.get_status(job_id)

    async def _run_upload_job(
        self,
        job_id: str,
        files: list[QueuedUploadFile],
        tool_name: str,
        processor: Callable[..., Awaitable[dict]],
        client_start_time: float | None,
        client_total_size: int | None,
    ) -> None:
        self._update(job_id, status="validating", progress=10)

        def progress_callback(status: str, progress: int) -> None:
            self._update(job_id, status=status, progress=progress)

        try:
            result = await processor(
                files=files,
                tool_name=tool_name,
                client_start_time=client_start_time,
                client_total_size=client_total_size,
                progress_callback=progress_callback,
            )
            status = "completed" if result.get("status") in {"success", "partial"} else "failed"
            error = None if status == "completed" else str(result.get("msg") or "Ingestion failed")
            self._update(job_id, status=status, progress=100, result=result, error=error)
        except asyncio.CancelledError:
            self._update(job_id, status="interrupted", error="Ingestion task was interrupted.")
            raise
        except Exception as exc:
            self._update(job_id, status="failed", progress=100, error=str(exc))

    def get_status(self, job_id: str) -> dict[str, Any]:
        self.cleanup()
        job = self._repository.get(job_id)
        if job is None:
            return {"job_id": job_id, "status": "not_found", "progress": 0, "error": "Job not found"}
        return dict(job)

    async def sse_events(self, job_id: str, *, interval_seconds: float = 0.5):
        while True:
            status = self.get_status(job_id)
            yield f"event: progress\ndata: {json.dumps(status, ensure_ascii=False)}\n\n"
            if status.get("status") in {*TERMINAL_INGESTION_STATUSES, "not_found"}:
                break
            await asyncio.sleep(interval_seconds)

    def cleanup(self) -> None:
        cutoff = time.time() - self.ttl_seconds
        self._repository.delete_stale_terminal(cutoff)

    def _update(self, job_id: str, **changes: Any) -> None:
        self._repository.update(job_id, updated_at=time.time(), **changes)


@lru_cache(maxsize=1)
def get_ingestion_queue() -> IngestionQueue:
    return IngestionQueue(ttl_seconds=3600)
