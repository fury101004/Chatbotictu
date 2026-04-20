from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from config.db import get_conn
from services.ictu_scope_service import is_ictu_related_query, normalize_scope_text


WEB_KB_TRUSTED_THRESHOLD = int(os.getenv("WEB_KB_TRUSTED_THRESHOLD", "30"))
WEB_KB_MIN_SCORE = int(os.getenv("WEB_KB_MIN_SCORE", "18"))
WEB_KB_TTL_DAYS = int(os.getenv("WEB_KB_TTL_DAYS", "30"))
WEB_KB_REALTIME_TTL_DAYS = int(os.getenv("WEB_KB_REALTIME_TTL_DAYS", "2"))
OFFICIAL_ICTU_DOMAIN = "ictu.edu.vn"
REALTIME_MARKERS = ("hom nay", "moi nhat", "tin moi", "tin tuc", "cap nhat", "thong bao moi")

NO_INFO_MARKERS = (
    "thong tin nay hien chua co trong tai lieu",
    "cau hoi nay nam ngoai pham vi ictu",
    "tro ly ai chua duoc cau hinh",
    "minh dang kiem tra them thong tin",
)


@dataclass(slots=True)
class WebKnowledgeMatch:
    entry_id: int
    question: str
    answer: str
    sources: list[str]
    source_text: str
    score: int
    status: str
    expires_at: str


def _now() -> datetime:
    return datetime.now()


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _parse_sources(value: str) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _is_official_ictu_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").casefold()
    return host == OFFICIAL_ICTU_DOMAIN or host.endswith(f".{OFFICIAL_ICTU_DOMAIN}")


def _sources_are_official(sources: list[str]) -> bool:
    return any(_is_official_ictu_url(source) for source in sources)


def _entry_hash(question: str, sources: list[str]) -> str:
    payload = normalize_scope_text(f"{question}\n{' '.join(sorted(sources))}")
    return hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", normalize_scope_text(text)) if len(token) > 1]


def _score_entry(query: str, *, question: str, answer: str, source_text: str, sources: list[str]) -> int:
    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return 0

    question_text = normalize_scope_text(question)
    answer_text = normalize_scope_text(answer)
    source_body = normalize_scope_text(source_text)
    source_url_text = normalize_scope_text(" ".join(sources))
    phrase = normalize_scope_text(query)

    score = 0
    for token in query_tokens:
        if token in question_text:
            score += 8
        if token in answer_text:
            score += 4
        if token in source_body:
            score += 3
        if token in source_url_text:
            score += 2

    if phrase and phrase in question_text:
        score += 18
    if phrase and phrase in answer_text:
        score += 10
    if _sources_are_official(sources):
        score += 5
    return score


def _valid_answer_for_cache(answer: str) -> bool:
    normalized = normalize_scope_text(answer or "")
    if len(normalized) < 20:
        return False
    return not any(marker in normalized for marker in NO_INFO_MARKERS)


def _is_realtime_query(query: str) -> bool:
    normalized = normalize_scope_text(query or "")
    return any(marker in normalized for marker in REALTIME_MARKERS)


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


def trusted_web_knowledge_count() -> int:
    ensure_web_knowledge_schema()
    now_text = _iso(_now())
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


def web_knowledge_ready() -> bool:
    return trusted_web_knowledge_count() >= WEB_KB_TRUSTED_THRESHOLD


def save_web_search_answer(
    *,
    question: str,
    answer: str,
    chunks: list[Any],
    rag_tool: str | None = None,
    rag_route: str | None = None,
    llm_model: str | None = None,
) -> dict[str, Any]:
    web_chunks = [
        chunk
        for chunk in chunks
        if (getattr(chunk, "metadata", {}) or {}).get("source_type") == "web_search"
    ]
    if not web_chunks or not is_ictu_related_query(question) or not _valid_answer_for_cache(answer):
        return {"saved": False, "reason": "not_cacheable"}

    sources = list(
        dict.fromkeys(
            str((getattr(chunk, "metadata", {}) or {}).get("source") or "").strip()
            for chunk in web_chunks
            if str((getattr(chunk, "metadata", {}) or {}).get("source") or "").strip()
        )
    )
    if not sources:
        return {"saved": False, "reason": "missing_sources"}

    source_text = "\n\n".join(str(getattr(chunk, "document", "") or "").strip() for chunk in web_chunks if getattr(chunk, "document", None))
    official = _sources_are_official(sources)
    status = "trusted" if official else "candidate"
    confidence_score = 0.85 if official else 0.55
    now = _now()
    ttl_days = WEB_KB_REALTIME_TTL_DAYS if _is_realtime_query(question) else WEB_KB_TTL_DAYS
    expires_at = _iso(now + timedelta(days=ttl_days))
    content_hash = _entry_hash(question, sources)

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
            question.strip(),
            answer.strip(),
            json.dumps(sources, ensure_ascii=False),
            source_text[:8000],
            rag_tool,
            rag_route,
            llm_model,
            confidence_score,
            _iso(now),
            _iso(now),
            expires_at,
        ),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return {"saved": True, "status": status, "entry_id": row_id, "trusted_count": trusted_web_knowledge_count()}


def search_trusted_web_knowledge(query: str, *, limit: int = 4) -> list[WebKnowledgeMatch]:
    if not is_ictu_related_query(query) or not web_knowledge_ready():
        return []

    ensure_web_knowledge_schema()
    now_text = _iso(_now())
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
        LIMIT 300
        """,
        (now_text,),
    )
    rows = cursor.fetchall()
    conn.close()

    scored: list[WebKnowledgeMatch] = []
    for row in rows:
        sources = _parse_sources(str(row["sources_json"] or "[]"))
        score = _score_entry(
            query,
            question=str(row["question"] or ""),
            answer=str(row["answer"] or ""),
            source_text=str(row["source_text"] or ""),
            sources=sources,
        )
        if score < WEB_KB_MIN_SCORE:
            continue
        scored.append(
            WebKnowledgeMatch(
                entry_id=int(row["id"]),
                question=str(row["question"] or ""),
                answer=str(row["answer"] or ""),
                sources=sources,
                source_text=str(row["source_text"] or ""),
                score=score,
                status=str(row["status"] or "trusted"),
                expires_at=str(row["expires_at"] or ""),
            )
        )

    scored.sort(key=lambda item: item.score, reverse=True)
    matches = scored[:limit]
    if matches:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.executemany(
            "UPDATE web_search_knowledge SET hit_count = hit_count + 1, updated_at = ? WHERE id = ?",
            [(_iso(_now()), match.entry_id) for match in matches],
        )
        conn.commit()
        conn.close()
    return matches
