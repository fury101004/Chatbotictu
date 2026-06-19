from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from config.rag_tools import RAG_TOOL_PROFILES
from config.settings import settings
from config.system_prompt import ensure_system_prompt_file, get_system_prompt


DB_PATH = Path(settings.DB_PATH)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES, timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _table_columns(cursor: sqlite3.Cursor, table_name: str) -> list[str]:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [column[1] for column in cursor.fetchall()]


def _ensure_chat_history_schema(cursor: sqlite3.Cursor) -> None:
    columns = _table_columns(cursor, "chat_history")
    if "session_id" not in columns:
        cursor.execute(
            "ALTER TABLE chat_history ADD COLUMN session_id TEXT NOT NULL DEFAULT 'default'"
        )
        columns.append("session_id")
    if "owner_username" not in columns:
        cursor.execute(
            "ALTER TABLE chat_history ADD COLUMN owner_username TEXT NOT NULL DEFAULT ''"
        )
        columns.append("owner_username")
    if "owner_role" not in columns:
        cursor.execute(
            "ALTER TABLE chat_history ADD COLUMN owner_role TEXT NOT NULL DEFAULT ''"
        )
        columns.append("owner_role")
    if "original_question" not in columns:
        cursor.execute(
            "ALTER TABLE chat_history ADD COLUMN original_question TEXT NOT NULL DEFAULT ''"
        )
        columns.append("original_question")
    if "rewritten_question" not in columns:
        cursor.execute(
            "ALTER TABLE chat_history ADD COLUMN rewritten_question TEXT NOT NULL DEFAULT ''"
        )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_history_session_id_id "
        "ON chat_history(session_id, id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_history_owner_id "
        "ON chat_history(owner_username, id)"
    )


def _ensure_chat_qa_review_schema(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_qa_review (
            entry_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending',
            tool_name TEXT,
            reason TEXT NOT NULL DEFAULT '',
            reviewer TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chat_qa_review_status_updated
        ON chat_qa_review(status, updated_at)
        """
    )


def _ensure_web_users_schema(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS web_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            username TEXT NOT NULL COLLATE NOCASE UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_web_users_username
        ON web_users(username COLLATE NOCASE)
        """
    )


def _ensure_chat_memory_schema(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_memory (
            memory_key TEXT PRIMARY KEY,
            messages_json TEXT NOT NULL DEFAULT '[]',
            expires_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chat_memory_expires_at
        ON chat_memory(expires_at)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chat_memory_updated_at
        ON chat_memory(updated_at)
        """
    )


def init_db() -> None:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT,
            content TEXT,
            timestamp TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    _ensure_chat_history_schema(cursor)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS uploaded_files (
            filename TEXT PRIMARY KEY,
            upload_time TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS uploaded_files_v2 (
            storage_path TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            upload_time TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS approved_chat_qa (
            entry_id TEXT PRIMARY KEY,
            question_row_id INTEGER,
            answer_row_id INTEGER,
            session_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            source_name TEXT NOT NULL,
            storage_path TEXT NOT NULL,
            approved_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    _ensure_chat_qa_review_schema(cursor)
    _ensure_web_users_schema(cursor)
    _ensure_chat_memory_schema(cursor)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS web_search_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL DEFAULT 'candidate',
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            sources_json TEXT NOT NULL DEFAULT '[]',
            source_text TEXT NOT NULL DEFAULT '',
            rag_tool TEXT,
            rag_route TEXT,
            llm_model TEXT,
            confidence_score REAL NOT NULL DEFAULT 0,
            hit_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            expires_at TEXT
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_web_search_knowledge_status_expires "
        "ON web_search_knowledge(status, expires_at)"
    )

    default_system_prompt = ensure_system_prompt_file()
    defaults = [
        ("bot_rules", default_system_prompt),
        ("chunk_size", "1000"),
        ("chunk_overlap", "200"),
    ]
    cursor.executemany("INSERT OR IGNORE INTO config VALUES (?, ?)", defaults)

    cursor.execute("SELECT storage_path FROM uploaded_files_v2 LIMIT 1")
    has_v2_rows = cursor.fetchone() is not None
    cursor.execute("SELECT filename, upload_time FROM uploaded_files")
    legacy_rows = cursor.fetchall()
    if legacy_rows and not has_v2_rows:
        cursor.executemany(
            """
            INSERT OR IGNORE INTO uploaded_files_v2 (storage_path, filename, tool_name, upload_time)
            VALUES (?, ?, ?, ?)
            """,
            [(filename, filename, "legacy_upload", upload_time) for filename, upload_time in legacy_rows],
        )

    conn.commit()
    conn.close()


def get_config(key: str, default: str = "") -> str:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM config WHERE key=?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default


def set_config(key: str, value: str) -> None:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO config VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def get_web_user_by_username(username: str) -> Dict[str, str] | None:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, full_name, username, password_hash, role, created_at
        FROM web_users
        WHERE username = ? COLLATE NOCASE
        LIMIT 1
        """,
        (str(username or "").strip(),),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    user_id, full_name, stored_username, password_hash, role, created_at = row
    return {
        "id": str(user_id),
        "full_name": str(full_name or ""),
        "username": str(stored_username or ""),
        "password_hash": str(password_hash or ""),
        "role": str(role or "user"),
        "created_at": str(created_at or ""),
    }


def get_web_user_by_id(user_id: int) -> Dict[str, str] | None:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, full_name, username, password_hash, role, created_at
        FROM web_users
        WHERE id = ?
        LIMIT 1
        """,
        (int(user_id),),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    row_id, full_name, stored_username, password_hash, role, created_at = row
    return {
        "id": str(row_id),
        "full_name": str(full_name or ""),
        "username": str(stored_username or ""),
        "password_hash": str(password_hash or ""),
        "role": str(role or "user"),
        "created_at": str(created_at or ""),
    }


def list_web_users() -> List[Dict[str, str]]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, full_name, username, role, created_at
        FROM web_users
        ORDER BY created_at DESC, id DESC
        """
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": str(user_id),
            "full_name": str(full_name or ""),
            "username": str(username or ""),
            "role": str(role or "user"),
            "created_at": str(created_at or ""),
        }
        for user_id, full_name, username, role, created_at in rows
    ]


def add_web_user(full_name: str, username: str, password_hash: str, role: str = "user") -> int:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO web_users (full_name, username, password_hash, role)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(full_name or "").strip(),
                str(username or "").strip(),
                str(password_hash or ""),
                str(role or "user").strip().lower() or "user",
            ),
        )
        row_id = cursor.lastrowid or 0
        conn.commit()
        return int(row_id)
    finally:
        conn.close()


def update_web_user(
    user_id: int,
    *,
    full_name: str,
    username: str,
    role: str,
    password_hash: str | None = None,
) -> bool:
    conn = get_conn()
    cursor = conn.cursor()
    if password_hash:
        cursor.execute(
            """
            UPDATE web_users
            SET full_name = ?, username = ?, role = ?, password_hash = ?
            WHERE id = ?
            """,
            (
                str(full_name or "").strip(),
                str(username or "").strip(),
                str(role or "user").strip().lower() or "user",
                str(password_hash or ""),
                int(user_id),
            ),
        )
    else:
        cursor.execute(
            """
            UPDATE web_users
            SET full_name = ?, username = ?, role = ?
            WHERE id = ?
            """,
            (
                str(full_name or "").strip(),
                str(username or "").strip(),
                str(role or "user").strip().lower() or "user",
                int(user_id),
            ),
        )
    changed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def delete_web_user(user_id: int) -> bool:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM web_users WHERE id = ?", (int(user_id),))
    changed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def _chat_history_columns(cursor: sqlite3.Cursor) -> list[str]:
    cursor.execute("PRAGMA table_info(chat_history)")
    return [column[1] for column in cursor.fetchall()]


def _chat_history_has_session_id(cursor: sqlite3.Cursor) -> bool:
    return "session_id" in _chat_history_columns(cursor)


def save_message(
    role: str,
    content: str,
    session_id: str = "default",
    owner_username: str = "",
    owner_role: str = "",
    original_question: str = "",
    rewritten_question: str = "",
) -> int:
    conn = get_conn()
    cursor = conn.cursor()
    columns = set(_chat_history_columns(cursor))

    if {
        "session_id",
        "owner_username",
        "owner_role",
        "original_question",
        "rewritten_question",
    }.issubset(columns):
        cursor.execute(
            """
            INSERT INTO chat_history (
                role, content, session_id, owner_username, owner_role,
                original_question, rewritten_question
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                role,
                content,
                session_id,
                str(owner_username or "").strip(),
                str(owner_role or "").strip().lower(),
                str(original_question or "").strip(),
                str(rewritten_question or "").strip(),
            ),
        )
    elif "session_id" in columns:
        cursor.execute(
            "INSERT INTO chat_history (role, content, session_id) VALUES (?, ?, ?)",
            (role, content, session_id),
        )
    else:
        cursor.execute(
            "INSERT INTO chat_history (role, content) VALUES (?, ?)",
            (role, content),
        )

    row_id = cursor.lastrowid or 0
    conn.commit()
    conn.close()
    return row_id


def add_uploaded_file(filename: str, tool_name: str, storage_path: str) -> None:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO uploaded_files_v2 (storage_path, filename, tool_name)
        VALUES (?, ?, ?)
        """,
        (storage_path, filename, tool_name),
    )
    conn.commit()
    conn.close()


def delete_uploaded_file(storage_path: str) -> None:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM uploaded_files_v2 WHERE storage_path = ?", (storage_path,))
    cursor.execute("DELETE FROM uploaded_files WHERE filename = ?", (storage_path,))
    conn.commit()
    conn.close()


def get_uploaded_files() -> List[Dict[str, str]]:
    conn = get_conn()
    cursor = conn.cursor()
    rows: list[tuple[str, str, str, str]] = []
    tables = {row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "uploaded_files_v2" in tables:
        cursor.execute(
            """
            SELECT filename, tool_name, storage_path, upload_time
            FROM uploaded_files_v2
            ORDER BY upload_time DESC
            """
        )
        rows = cursor.fetchall()

    if not rows and "uploaded_files" in tables and "filename" in _table_columns(cursor, "uploaded_files"):
        cursor.execute("SELECT filename, upload_time FROM uploaded_files ORDER BY upload_time DESC")
        rows = [(filename, "legacy_upload", filename, upload_time) for filename, upload_time in cursor.fetchall()]
    conn.close()

    result: List[Dict[str, str]] = []
    for filename, tool_name, storage_path, upload_time in rows:
        display_time = upload_time.split(".")[0] if upload_time else ""
        try:
            parsed = datetime.strptime(display_time, "%Y-%m-%d %H:%M:%S")
            display_time = parsed.strftime("%d/%m %H:%M")
        except Exception:
            display_time = "Vừa xong"
        tool_label = str(RAG_TOOL_PROFILES.get(tool_name, {}).get("label", tool_name)).replace("_", " ")
        result.append(
            {
                "filename": filename,
                "tool_name": tool_name,
                "tool_label": tool_label,
                "storage_path": storage_path,
                "time": display_time,
            }
        )
    return result


def clear_uploaded_files() -> None:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM uploaded_files_v2")
    cursor.execute("DELETE FROM uploaded_files")
    conn.commit()
    conn.close()


def upsert_approved_chat_qa(
    *,
    entry_id: str,
    question_row_id: int,
    answer_row_id: int,
    session_id: str,
    tool_name: str,
    question: str,
    answer: str,
    source_name: str,
    storage_path: str,
) -> None:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO approved_chat_qa (
            entry_id,
            question_row_id,
            answer_row_id,
            session_id,
            tool_name,
            question,
            answer,
            source_name,
            storage_path,
            approved_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
        """,
        (
            entry_id,
            question_row_id,
            answer_row_id,
            session_id,
            tool_name,
            question,
            answer,
            source_name,
            storage_path,
        ),
    )
    conn.commit()
    conn.close()


def get_approved_chat_qas() -> List[Dict[str, str]]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT entry_id, session_id, tool_name, question, answer, source_name, storage_path, approved_at
        FROM approved_chat_qa
        ORDER BY approved_at DESC, entry_id DESC
        """
    )
    rows = cursor.fetchall()
    conn.close()

    result: List[Dict[str, str]] = []
    for entry_id, session_id, tool_name, question, answer, source_name, storage_path, approved_at in rows:
        display_time = approved_at.split(".")[0] if approved_at else ""
        try:
            parsed = datetime.strptime(display_time, "%Y-%m-%d %H:%M:%S")
            display_time = parsed.strftime("%d/%m %H:%M")
        except Exception:
            display_time = "Vừa xong"
        result.append(
            {
                "entry_id": entry_id,
                "session_id": session_id,
                "tool_name": tool_name,
                "question": question,
                "answer": answer,
                "source_name": source_name,
                "storage_path": storage_path,
                "approved_at": approved_at,
                "time": display_time,
            }
        )
    return result


def get_approved_chat_entry_ids() -> set[str]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT entry_id FROM approved_chat_qa")
    rows = {str(entry_id) for (entry_id,) in cursor.fetchall()}
    conn.close()
    return rows


def upsert_chat_qa_review_state(
    *,
    entry_id: str,
    status: str,
    tool_name: str = "",
    reason: str = "",
    reviewer: str = "",
) -> None:
    normalized_status = status if status in {"pending", "approved", "rejected"} else "pending"
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO chat_qa_review (entry_id, status, tool_name, reason, reviewer, updated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))
        ON CONFLICT(entry_id) DO UPDATE SET
            status = excluded.status,
            tool_name = CASE
                WHEN excluded.tool_name != '' THEN excluded.tool_name
                ELSE chat_qa_review.tool_name
            END,
            reason = excluded.reason,
            reviewer = excluded.reviewer,
            updated_at = datetime('now', 'localtime')
        """,
        (entry_id, normalized_status, tool_name, reason, reviewer),
    )
    conn.commit()
    conn.close()


def get_chat_qa_review_states() -> List[Dict[str, str]]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT entry_id, status, COALESCE(tool_name, ''), reason, reviewer, created_at, updated_at
        FROM chat_qa_review
        ORDER BY updated_at DESC, entry_id DESC
        """
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "entry_id": str(entry_id),
            "status": str(status),
            "tool_name": str(tool_name or ""),
            "reason": str(reason or ""),
            "reviewer": str(reviewer or ""),
            "created_at": str(created_at or ""),
            "updated_at": str(updated_at or ""),
        }
        for entry_id, status, tool_name, reason, reviewer, created_at, updated_at in rows
    ]


def get_chat_history(session_id: str = "default") -> List[Dict[str, str]]:
    conn = get_conn()
    cursor = conn.cursor()

    columns = set(_chat_history_columns(cursor))
    has_question_debug = {"original_question", "rewritten_question"}.issubset(columns)
    original_question_expr = "COALESCE(original_question, '')" if has_question_debug else "''"
    rewritten_question_expr = "COALESCE(rewritten_question, '')" if has_question_debug else "''"

    if _chat_history_has_session_id(cursor):
        cursor.execute(
            f"""
            SELECT role, content, {original_question_expr}, {rewritten_question_expr}
            FROM chat_history
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        )
    else:
        cursor.execute(
            f"""
            SELECT role, content, {original_question_expr}, {rewritten_question_expr}
            FROM chat_history
            ORDER BY id ASC
            """
        )

    rows = cursor.fetchall()
    conn.close()

    history: List[Dict[str, str]] = [{"role": "system", "content": get_system_prompt()}]
    for role, content, original_question, rewritten_question in rows:
        if role == "user":
            history.append(
                {
                    "role": "user",
                    "content": content,
                    "original_question": original_question or content,
                    "rewritten_question": rewritten_question or content,
                }
            )
        elif role in ("bot", "assistant"):
            history.append({"role": "assistant", "content": content})
    return history


init_db()
