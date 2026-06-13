from __future__ import annotations

import hashlib
import json
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

import aiosqlite

from config.settings import settings


class MemoryStore:
    def __init__(
        self,
        *,
        db_path: str | Path | None = None,
        default_ttl_seconds: int | None = None,
        max_messages: int | None = None,
        max_sessions: int | None = None,
    ) -> None:
        self.db_path = Path(db_path or settings.DB_PATH)
        self.default_ttl_seconds = max(
            1,
            int(default_ttl_seconds or settings.CHAT_MEMORY_TTL_SECONDS),
        )
        self.max_messages = max(2, int(max_messages or settings.CHAT_MEMORY_MAX_MESSAGES))
        self.max_sessions = max(1, int(max_sessions or settings.CHAT_MEMORY_MAX_SESSIONS))

    @property
    def backend(self) -> str:
        return "sqlite"

    async def save(
        self,
        session_id: str,
        messages: list[dict],
        ttl_seconds: int | None = None,
    ) -> None:
        memory_key = self._key(session_id)
        normalized = self._normalize_messages(messages)
        now = int(time.time())
        updated_at = time.time_ns()
        ttl = max(1, int(ttl_seconds or self.default_ttl_seconds))

        async with self._connect() as conn:
            await self._ensure_schema(conn)
            await conn.execute(
                """
                INSERT INTO chat_memory (memory_key, messages_json, expires_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(memory_key) DO UPDATE SET
                    messages_json = excluded.messages_json,
                    expires_at = excluded.expires_at,
                    updated_at = excluded.updated_at
                """,
                (
                    memory_key,
                    json.dumps(normalized, ensure_ascii=False),
                    now + ttl,
                    updated_at,
                ),
            )
            await self._cleanup(conn, now)
            await conn.commit()

    async def load(self, session_id: str) -> list[dict]:
        memory_key = self._key(session_id)
        now = int(time.time())

        async with self._connect() as conn:
            await self._ensure_schema(conn)
            cursor = await conn.execute(
                """
                SELECT messages_json, expires_at
                FROM chat_memory
                WHERE memory_key = ?
                LIMIT 1
                """,
                (memory_key,),
            )
            row = await cursor.fetchone()
            await cursor.close()

            if not row:
                return []
            if int(row[1] or 0) <= now:
                await conn.execute("DELETE FROM chat_memory WHERE memory_key = ?", (memory_key,))
                await conn.commit()
                return []

            try:
                payload = json.loads(str(row[0] or "[]"))
            except json.JSONDecodeError:
                await conn.execute("DELETE FROM chat_memory WHERE memory_key = ?", (memory_key,))
                await conn.commit()
                return []

        return self._normalize_messages(payload if isinstance(payload, list) else [])

    async def delete(self, session_id: str) -> None:
        memory_key = self._key(session_id)
        async with self._connect() as conn:
            await self._ensure_schema(conn)
            await conn.execute("DELETE FROM chat_memory WHERE memory_key = ?", (memory_key,))
            await conn.commit()

    def _connect(self) -> aiosqlite.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return aiosqlite.connect(self.db_path, timeout=30)

    async def _ensure_schema(self, conn: aiosqlite.Connection) -> None:
        await conn.execute("PRAGMA busy_timeout = 5000")
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_memory (
                memory_key TEXT PRIMARY KEY,
                messages_json TEXT NOT NULL DEFAULT '[]',
                expires_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_memory_expires_at
            ON chat_memory(expires_at)
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_memory_updated_at
            ON chat_memory(updated_at)
            """
        )

    async def _cleanup(self, conn: aiosqlite.Connection, now: int) -> None:
        await conn.execute("DELETE FROM chat_memory WHERE expires_at <= ?", (now,))
        await conn.execute(
            """
            DELETE FROM chat_memory
            WHERE memory_key IN (
                SELECT memory_key
                FROM chat_memory
                ORDER BY updated_at DESC
                LIMIT -1 OFFSET ?
            )
            """,
            (self.max_sessions,),
        )

    def _key(self, session_id: str) -> str:
        cleaned = str(session_id or "anonymous").strip() or "anonymous"
        return f"chat_memory:{cleaned}"

    def _normalize_messages(self, messages: list[dict]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in messages[-self.max_messages :]:
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "").strip()
            if role and content:
                normalized_item: dict[str, Any] = {"role": role, "content": content}
                sources = [
                    str(source or "").strip()
                    for source in item.get("sources") or []
                    if str(source or "").strip()
                ]
                if sources:
                    normalized_item["sources"] = list(dict.fromkeys(sources))[:25]
                normalized.append(normalized_item)
        return normalized


def stable_session_id(user_id: str | None = None, anonymous_id: str | None = None) -> str:
    if user_id:
        digest = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()
        return f"user:{digest}"
    if anonymous_id:
        digest = hashlib.sha256(str(anonymous_id).encode("utf-8")).hexdigest()
        return f"anon:{digest}"
    return f"anon:{uuid.uuid4()}"


@lru_cache(maxsize=1)
def get_default_memory_store() -> MemoryStore:
    return MemoryStore()
