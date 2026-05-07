from __future__ import annotations

from datetime import datetime
from typing import Any

from config.db import get_chat_history as _get_chat_history
from config.db import get_conn, save_message as _save_message


def save_conversation_message(role: str, content: str, *, session_id: str = "default") -> None:
    _save_message(role, content, session_id=session_id)


def load_chat_history(session_id: str = "default") -> list[dict[str, str]]:
    return _get_chat_history(session_id=session_id)


def _chat_history_has_session_id(cursor) -> bool:
    cursor.execute("PRAGMA table_info(chat_history)")
    return "session_id" in [column[1] for column in cursor.fetchall()]


def list_chat_history_rows() -> list[dict[str, Any]]:
    conn = get_conn()
    cursor = conn.cursor()

    if _chat_history_has_session_id(cursor):
        cursor.execute(
            """
            SELECT id, role, content, timestamp, session_id
            FROM chat_history
            ORDER BY id ASC
            """
        )
        rows = [
            {
                "id": row_id,
                "role": role,
                "content": content or "",
                "timestamp": timestamp or "",
                "session_id": session_id or "default",
            }
            for row_id, role, content, timestamp, session_id in cursor.fetchall()
        ]
    else:
        cursor.execute(
            """
            SELECT id, role, content, timestamp
            FROM chat_history
            ORDER BY id ASC
            """
        )
        rows = [
            {
                "id": row_id,
                "role": role,
                "content": content or "",
                "timestamp": timestamp or "",
                "session_id": "default",
            }
            for row_id, role, content, timestamp in cursor.fetchall()
        ]

    conn.close()
    return rows


def get_chat_history_page(*, page: int, per_page: int = 50) -> dict[str, Any]:
    offset = max(page - 1, 0) * per_page
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM chat_history")
    total = int(cursor.fetchone()[0] or 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    cursor.execute(
        "SELECT role, content, timestamp FROM chat_history ORDER BY id DESC LIMIT ? OFFSET ?",
        (per_page, offset),
    )
    rows = cursor.fetchall()
    conn.close()

    history_rows: list[dict[str, str]] = []
    for role, content, timestamp in rows:
        try:
            time_str = datetime.strptime(str(timestamp or "").split(".")[0], "%Y-%m-%d %H:%M:%S").strftime("%d/%m %H:%M")
        except Exception:
            time_str = "Vua xong"
        history_rows.append(
            {
                "role": str(role or ""),
                "content": str(content or ""),
                "time": time_str,
            }
        )

    return {
        "history": history_rows,
        "page": page,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
    }
