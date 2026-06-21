from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import BackgroundTasks

from config.settings import settings
from repositories.ingestion_repository import IngestionJobRepository, TERMINAL_INGESTION_STATUSES


@dataclass(slots=True)
class QueuedUploadFile:
    filename: str
    content: bytes | None = None
    content_type: str = ""
    checkpoint_file: Path | None = None

    async def read(self) -> bytes:
        if self.content is not None:
            return self.content
        if self.checkpoint_file is not None:
            return self.checkpoint_file.read_bytes()
        return b""


class IngestionQueue:
    def __init__(
        self,
        *,
        ttl_seconds: int = 3600,
        db_path: str | None = None,
        checkpoint_root: str | Path | None = None,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self._repository = IngestionJobRepository(db_path)
        self._checkpoint_root = Path(checkpoint_root or settings.DATA_DIR / "ingestion_checkpoints")
        self._checkpoint_root.mkdir(parents=True, exist_ok=True)
        self._active_tasks: set[asyncio.Task] = set()

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
        checkpoint_path = self._create_checkpoint(
            job_id=job_id,
            files=snapshots,
            tool_name=tool_name,
            client_start_time=client_start_time,
            client_total_size=client_total_size,
        )
        job = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0,
            "error": None,
            "result": None,
            "tool_name": tool_name,
            "file_count": len(snapshots),
            "total_size": total_size,
            "checkpoint_path": str(checkpoint_path),
            "created_at": now,
            "updated_at": now,
        }
        try:
            self._repository.create(job)
        except Exception:
            self._remove_checkpoint(checkpoint_path)
            raise
        background_tasks.add_task(
            self._run_upload_job,
            job_id,
            snapshots,
            tool_name,
            processor,
            client_start_time,
            client_total_size,
            checkpoint_path,
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
        checkpoint_path: Path,
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
            self._update(
                job_id,
                status=status,
                progress=100,
                result=result,
                error=error,
                checkpoint_path=None,
            )
            self._remove_checkpoint(checkpoint_path)
        except asyncio.CancelledError:
            self._update(
                job_id,
                status="queued",
                error="Ingestion paused before completion; it will resume after restart.",
            )
            raise
        except Exception as exc:
            self._update(
                job_id,
                status="failed",
                progress=100,
                error=str(exc),
                checkpoint_path=None,
            )
            self._remove_checkpoint(checkpoint_path)

    async def resume_pending_uploads(
        self,
        *,
        processor: Callable[..., Awaitable[dict]],
    ) -> int:
        """Resume every non-terminal upload that has a durable checkpoint.

        The queue stores upload bytes outside SQLite.  A restart can therefore
        re-run the same idempotent document ingestion operation instead of
        discarding the payload that was originally held in memory.
        """
        scheduled = 0
        for job in self._repository.list_recoverable():
            job_id = str(job["job_id"])
            checkpoint_path = Path(str(job.get("checkpoint_path") or ""))
            try:
                files, checkpoint = self._load_checkpoint(checkpoint_path)
            except Exception as exc:
                self._update(
                    job_id,
                    status="interrupted",
                    error=f"Cannot resume ingestion: durable checkpoint is unavailable ({exc}).",
                    checkpoint_path=None,
                )
                self._remove_checkpoint(checkpoint_path)
                continue

            # Convert every old in-flight state to a single restartable state
            # before claiming it. This keeps status polling meaningful while
            # the resumed task is being scheduled.
            self._update(
                job_id,
                status="queued",
                error="Queued for resume from durable checkpoint after restart.",
            )
            if not self._repository.claim_for_resume(job_id):
                continue

            task = asyncio.create_task(
                self._run_upload_job(
                    job_id,
                    files,
                    str(checkpoint.get("tool_name") or job.get("tool_name") or ""),
                    processor,
                    checkpoint.get("client_start_time"),
                    checkpoint.get("client_total_size"),
                    checkpoint_path,
                ),
                name=f"resume-ingestion-{job_id}",
            )
            self._track_task(task)
            scheduled += 1
        return scheduled

    async def wait_for_active_jobs(self) -> None:
        """Wait for scheduled resume tasks; primarily useful in integration tests."""
        while self._active_tasks:
            await asyncio.gather(*tuple(self._active_tasks), return_exceptions=True)

    def _track_task(self, task: asyncio.Task) -> None:
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)

    def _create_checkpoint(
        self,
        *,
        job_id: str,
        files: list[QueuedUploadFile],
        tool_name: str,
        client_start_time: float | None,
        client_total_size: int | None,
    ) -> Path:
        checkpoint_path = self._checkpoint_root / job_id
        files_path = checkpoint_path / "files"
        files_path.mkdir(parents=True, exist_ok=False)
        manifest_files: list[dict[str, Any]] = []
        try:
            for index, upload in enumerate(files):
                original_name = Path(upload.filename).name or f"upload-{index + 1}.txt"
                stored_name = f"{index:03d}-{original_name}"
                target = files_path / stored_name
                content = upload.content or b""
                with target.open("wb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                manifest_files.append(
                    {
                        "filename": upload.filename,
                        "content_type": upload.content_type,
                        "path": str(Path("files") / stored_name),
                        "size": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                )

            manifest = {
                "version": 1,
                "job_id": job_id,
                "tool_name": str(tool_name or ""),
                "client_start_time": client_start_time,
                "client_total_size": client_total_size,
                "files": manifest_files,
            }
            temporary_manifest = checkpoint_path / "manifest.json.tmp"
            with temporary_manifest.open("w", encoding="utf-8") as handle:
                json.dump(manifest, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            temporary_manifest.replace(checkpoint_path / "manifest.json")
            return checkpoint_path
        except Exception:
            self._remove_checkpoint(checkpoint_path)
            raise

    def _load_checkpoint(self, checkpoint_path: Path) -> tuple[list[QueuedUploadFile], dict[str, Any]]:
        resolved_checkpoint = self._validated_checkpoint_path(checkpoint_path)
        manifest_path = resolved_checkpoint / "manifest.json"
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        if int(manifest.get("version") or 0) != 1 or not isinstance(manifest.get("files"), list):
            raise ValueError("invalid checkpoint manifest")

        files: list[QueuedUploadFile] = []
        for item in manifest["files"]:
            relative_path = Path(str(item.get("path") or ""))
            if not relative_path.parts or relative_path.is_absolute() or ".." in relative_path.parts:
                raise ValueError("invalid checkpoint file path")
            checkpoint_file = (resolved_checkpoint / relative_path).resolve()
            if resolved_checkpoint not in checkpoint_file.parents or not checkpoint_file.is_file():
                raise ValueError("checkpoint file is missing")
            expected_size = int(item.get("size") or 0)
            if checkpoint_file.stat().st_size != expected_size:
                raise ValueError("checkpoint file size does not match manifest")
            actual_checksum = hashlib.sha256(checkpoint_file.read_bytes()).hexdigest()
            if actual_checksum != str(item.get("sha256") or ""):
                raise ValueError("checkpoint file checksum does not match manifest")
            files.append(
                QueuedUploadFile(
                    filename=str(item.get("filename") or checkpoint_file.name),
                    content_type=str(item.get("content_type") or ""),
                    checkpoint_file=checkpoint_file,
                )
            )
        return files, manifest

    def _validated_checkpoint_path(self, checkpoint_path: Path) -> Path:
        root = self._checkpoint_root.resolve()
        candidate = checkpoint_path.resolve()
        if candidate == root or root not in candidate.parents:
            raise ValueError("checkpoint path is outside the ingestion checkpoint directory")
        return candidate

    def _remove_checkpoint(self, checkpoint_path: Path | str | None) -> None:
        if not checkpoint_path:
            return
        try:
            candidate = self._validated_checkpoint_path(Path(checkpoint_path))
        except (OSError, ValueError):
            return
        if candidate.exists():
            shutil.rmtree(candidate)

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
        for checkpoint_path in self._repository.delete_stale_terminal(cutoff):
            self._remove_checkpoint(checkpoint_path)

    def _update(self, job_id: str, **changes: Any) -> None:
        self._repository.update(job_id, updated_at=time.time(), **changes)


@lru_cache(maxsize=1)
def get_ingestion_queue() -> IngestionQueue:
    return IngestionQueue(ttl_seconds=3600)
