from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from config.settings import settings

try:
    import aiosqlite
except Exception:  # pragma: no cover - optional until dependencies are installed.
    aiosqlite = None


class EvalTracker:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or (settings.DATA_DIR / "eval_log.db"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._schema_ready = False

    async def log_response(
        self,
        *,
        query: str,
        answer_length: int,
        sources_returned: int,
        latency_ms: int,
        has_sources: bool,
        user_thumbs_up: bool | None = None,
    ) -> None:
        await self._ensure_schema()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO eval_log (
                    timestamp, query, answer_length, sources_returned,
                    latency_ms, has_sources, user_thumbs_up
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    str(query or ""),
                    int(answer_length),
                    int(sources_returned),
                    int(latency_ms),
                    1 if has_sources else 0,
                    None if user_thumbs_up is None else 1 if user_thumbs_up else 0,
                ),
            )
            await db.commit()

    async def metrics(self, *, hours: int = 24) -> dict[str, Any]:
        await self._ensure_schema()
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute(
                    """
                    SELECT
                        COUNT(*) AS total_queries,
                        COALESCE(AVG(latency_ms), 0) AS avg_latency_ms,
                        COALESCE(AVG(has_sources), 0) AS source_hit_rate,
                        SUM(CASE WHEN user_thumbs_up IS NOT NULL THEN 1 ELSE 0 END) AS rated_queries,
                        SUM(CASE WHEN user_thumbs_up = 1 THEN 1 ELSE 0 END) AS thumbs_up_queries
                    FROM eval_log
                    WHERE timestamp >= ?
                    """,
                    (since,),
                )
            ).fetchone()
            failing_rows = await (
                await db.execute(
                    """
                    SELECT query
                    FROM eval_log
                    WHERE timestamp >= ? AND (has_sources = 0 OR user_thumbs_up = 0)
                    ORDER BY timestamp DESC
                    LIMIT 20
                    """,
                    (since,),
                )
            ).fetchall()

        rated = int(row["rated_queries"] or 0)
        thumbs_up = int(row["thumbs_up_queries"] or 0)
        return {
            "total_queries": int(row["total_queries"] or 0),
            "avg_latency_ms": round(float(row["avg_latency_ms"] or 0), 2),
            "source_hit_rate": round(float(row["source_hit_rate"] or 0), 4),
            "thumbs_up_rate": round((thumbs_up / rated) if rated else 0.0, 4),
            "failing_queries": [str(item["query"]) for item in failing_rows],
        }

    async def export_csv(self) -> str:
        await self._ensure_schema()
        output = io.StringIO()
        writer = csv.writer(output)
        headers = [
            "timestamp",
            "query",
            "answer_length",
            "sources_returned",
            "latency_ms",
            "has_sources",
            "user_thumbs_up",
        ]
        writer.writerow(headers)

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT timestamp, query, answer_length, sources_returned,
                       latency_ms, has_sources, user_thumbs_up
                FROM eval_log
                ORDER BY timestamp ASC
                """
            ) as cursor:
                async for row in cursor:
                    writer.writerow(row)
        return output.getvalue()

    async def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        if aiosqlite is None:
            raise RuntimeError("aiosqlite is required for EvalTracker. Install it with `pip install aiosqlite`.")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS eval_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    query TEXT NOT NULL,
                    answer_length INTEGER NOT NULL,
                    sources_returned INTEGER NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    has_sources INTEGER NOT NULL,
                    user_thumbs_up INTEGER NULL
                )
                """
            )
            await db.commit()
        self._schema_ready = True


@lru_cache(maxsize=1)
def get_eval_tracker() -> EvalTracker:
    return EvalTracker()

