from __future__ import annotations

import sqlite3
from typing import Any

from config.db import get_conn


def ensure_web_knowledge_schema() -> None:
    conn = get_conn()
    cursor = conn.cursor()
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
    conn.commit()
    conn.close()


def count_trusted_web_knowledge(now_text: str) -> int:
    ensure_web_knowledge_schema()
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM web_search_knowledge
        WHERE status = 'trusted'
          AND (expires_at IS NULL OR expires_at = '' OR expires_at > ?)
        """,
        (now_text,),
    )
    count = int(cursor.fetchone()[0] or 0)
    conn.close()
    return count


def upsert_web_knowledge_entry(
    *,
    content_hash: str,
    status: str,
    question: str,
    answer: str,
    sources_json: str,
    source_text: str,
    rag_tool: str | None,
    rag_route: str | None,
    llm_model: str | None,
    confidence_score: float,
    created_at: str,
    updated_at: str,
    expires_at: str,
) -> int | None:
    ensure_web_knowledge_schema()
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO web_search_knowledge (
            content_hash, status, question, answer, sources_json, source_text,
            rag_tool, rag_route, llm_model, confidence_score, hit_count,
            created_at, updated_at, expires_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
        ON CONFLICT(content_hash) DO UPDATE SET
            status = CASE
                WHEN web_search_knowledge.status = 'trusted' THEN 'trusted'
                ELSE excluded.status
            END,
            answer = excluded.answer,
            sources_json = excluded.sources_json,
            source_text = excluded.source_text,
            rag_tool = excluded.rag_tool,
            rag_route = excluded.rag_route,
            llm_model = excluded.llm_model,
            confidence_score = MAX(web_search_knowledge.confidence_score, excluded.confidence_score),
            updated_at = excluded.updated_at,
            expires_at = excluded.expires_at
        """,
        (
            content_hash,
            status,
            question,
            answer,
            sources_json,
            source_text,
            rag_tool,
            rag_route,
            llm_model,
            confidence_score,
            created_at,
            updated_at,
            expires_at,
        ),
    )
    conn.commit()
    cursor.execute(
        "SELECT id FROM web_search_knowledge WHERE content_hash = ?",
        (content_hash,),
    )
    row = cursor.fetchone()
    conn.close()
    return int(row[0]) if row else None


def list_trusted_web_knowledge_rows(now_text: str, *, limit: int = 300) -> list[sqlite3.Row]:
    ensure_web_knowledge_schema()
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, question, answer, sources_json, source_text, status, expires_at
        FROM web_search_knowledge
        WHERE status = 'trusted'
          AND (expires_at IS NULL OR expires_at = '' OR expires_at > ?)
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (now_text, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def increment_web_knowledge_hits(entry_ids: list[int], *, updated_at: str) -> None:
    if not entry_ids:
        return
    conn = get_conn()
    cursor = conn.cursor()
    cursor.executemany(
        "UPDATE web_search_knowledge SET hit_count = hit_count + 1, updated_at = ? WHERE id = ?",
        [(updated_at, entry_id) for entry_id in entry_ids],
    )
    conn.commit()
    conn.close()
