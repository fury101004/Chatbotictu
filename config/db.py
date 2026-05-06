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
    return sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)


def _table_columns(cursor: sqlite3.Cursor, table_name: str) -> list[str]:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [column[1] for column in cursor.fetchall()]


def _ensure_chat_history_schema(cursor: sqlite3.Cursor) -> None:
    columns = _table_columns(cursor, "chat_history")
    if "session_id" not in columns:
        cursor.execute(
            "ALTER TABLE chat_history ADD COLUMN session_id TEXT NOT NULL DEFAULT 'default'"
        )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_history_session_id_id "
        "ON chat_history(session_id, id)"
    )


def init_db() -> None:
    conn = get_conn()
    cursor = conn.cursor()
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


def _chat_history_has_session_id(cursor: sqlite3.Cursor) -> bool:
    cursor.execute("PRAGMA table_info(chat_history)")
    columns = [column[1] for column in cursor.fetchall()]
    return "session_id" in columns


def save_message(role: str, content: str, session_id: str = "default") -> None:
    conn = get_conn()
    cursor = conn.cursor()

    if _chat_history_has_session_id(cursor):
        cursor.execute(
            "INSERT INTO chat_history (role, content, session_id) VALUES (?, ?, ?)",
            (role, content, session_id),
        )
    else:
        cursor.execute(
            "INSERT INTO chat_history (role, content) VALUES (?, ?)",
            (role, content),
        )

    conn.commit()
    conn.close()


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


def get_chat_history(session_id: str = "default") -> List[Dict[str, str]]:
    conn = get_conn()
    cursor = conn.cursor()

    if _chat_history_has_session_id(cursor):
        cursor.execute(
            """
            SELECT role, content FROM chat_history
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        )
    else:
        cursor.execute(
            """
            SELECT role, content FROM chat_history
            ORDER BY id ASC
            """
        )

    rows = cursor.fetchall()
    conn.close()

    history: List[Dict[str, str]] = [{"role": "system", "content": get_system_prompt()}]
    for role, content in rows:
        if role == "user":
            history.append({"role": "user", "content": content})
        elif role in ("bot", "assistant"):
            history.append({"role": "assistant", "content": content})
    return history


init_db()
