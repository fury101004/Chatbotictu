from __future__ import annotations

import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from config.settings import settings


TERMINAL_INGESTION_STATUSES = {"completed", "failed", "interrupted"}


class IngestionJobRepository:
    def __init__(self, db_path: str | Path | None = None, *, interrupt_existing: bool = True) -> None:
        self.db_path = Path(db_path or settings.DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        if interrupt_existing:
            self.interrupt_unfinished()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    tool_name TEXT NOT NULL DEFAULT '',
                    file_count INTEGER NOT NULL DEFAULT 0,
                    total_size INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status_updated "
                "ON ingestion_jobs(status, updated_at)"
            )
            connection.commit()

    def create(self, job: dict[str, Any]) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO ingestion_jobs (
                    job_id, status, progress, tool_name, file_count, total_size,
                    result_json, error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job["job_id"],
                    job["status"],
                    int(job.get("progress", 0)),
                    str(job.get("tool_name") or ""),
                    int(job.get("file_count", 0)),
                    int(job.get("total_size", 0)),
                    json.dumps(job.get("result"), ensure_ascii=False) if job.get("result") is not None else None,
                    job.get("error"),
                    float(job["created_at"]),
                    float(job["updated_at"]),
                ),
            )
            connection.commit()

    def update(self, job_id: str, **changes: Any) -> None:
        current = self.get(job_id)
        if current is None:
            return
        current.update(changes)
        current["updated_at"] = float(changes.get("updated_at") or time.time())
        with closing(self._connect()) as connection:
            connection.execute(
                """
                UPDATE ingestion_jobs
                SET status = ?, progress = ?, result_json = ?, error = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (
                    current["status"],
                    int(current.get("progress", 0)),
                    json.dumps(current.get("result"), ensure_ascii=False) if current.get("result") is not None else None,
                    current.get("error"),
                    current["updated_at"],
                    job_id,
                ),
            )
            connection.commit()

    def get(self, job_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT job_id, status, progress, tool_name, file_count, total_size,
                       result_json, error, created_at, updated_at
                FROM ingestion_jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "job_id": str(row["job_id"]),
            "status": str(row["status"]),
            "progress": int(row["progress"]),
            "tool_name": str(row["tool_name"]),
            "file_count": int(row["file_count"]),
            "total_size": int(row["total_size"]),
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": str(row["error"]) if row["error"] else None,
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
        }

    def interrupt_unfinished(self) -> int:
        placeholders = ", ".join("?" for _ in TERMINAL_INGESTION_STATUSES)
        now = time.time()
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                f"""
                UPDATE ingestion_jobs
                SET status = 'interrupted',
                    error = COALESCE(error, 'Process restarted before ingestion completed.'),
                    updated_at = ?
                WHERE status NOT IN ({placeholders})
                """,
                (now, *sorted(TERMINAL_INGESTION_STATUSES)),
            )
            connection.commit()
            return int(cursor.rowcount or 0)

    def delete_stale_terminal(self, cutoff: float) -> None:
        placeholders = ", ".join("?" for _ in TERMINAL_INGESTION_STATUSES)
        with closing(self._connect()) as connection:
            connection.execute(
                f"DELETE FROM ingestion_jobs WHERE updated_at < ? AND status IN ({placeholders})",
                (cutoff, *sorted(TERMINAL_INGESTION_STATUSES)),
            )
            connection.commit()
