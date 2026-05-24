from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from config.settings import settings


FEEDBACK_DB_PATH = Path(settings.DATA_DIR) / "user_feedback.db"


async def _ensure_feedback_schema(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            session_id TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            thumbs_up INTEGER NOT NULL,
            comment TEXT
        )
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_feedback_timestamp
        ON user_feedback(timestamp)
        """
    )
    await conn.commit()


async def save_user_feedback(
    *,
    session_id: str,
    question: str,
    answer: str,
    thumbs_up: bool,
    comment: str = "",
) -> int:
    FEEDBACK_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat()
    async with aiosqlite.connect(FEEDBACK_DB_PATH) as conn:
        await _ensure_feedback_schema(conn)
        cursor = await conn.execute(
            """
            INSERT INTO user_feedback (
                timestamp, session_id, question, answer, thumbs_up, comment
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                str(session_id or "").strip(),
                str(question or "").strip(),
                str(answer or "").strip(),
                1 if thumbs_up else 0,
                str(comment or "").strip() or None,
            ),
        )
        await conn.commit()
        return int(cursor.lastrowid or 0)


async def get_feedback_summary() -> dict[str, Any]:
    FEEDBACK_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(FEEDBACK_DB_PATH) as conn:
        await _ensure_feedback_schema(conn)
        cursor = await conn.execute(
            """
            SELECT
                COUNT(*) AS total_feedback,
                COALESCE(SUM(CASE WHEN thumbs_up = 1 THEN 1 ELSE 0 END), 0) AS positive_feedback,
                COALESCE(SUM(CASE WHEN thumbs_up = 0 THEN 1 ELSE 0 END), 0) AS negative_feedback
            FROM user_feedback
            """
        )
        row = await cursor.fetchone()

    total = int(row[0] or 0) if row else 0
    positive = int(row[1] or 0) if row else 0
    negative = int(row[2] or 0) if row else 0
    positive_rate = round((positive / total) * 100, 2) if total else 0.0
    return {
        "total_feedback": total,
        "positive_feedback": positive,
        "negative_feedback": negative,
        "positive_rate": positive_rate,
    }
