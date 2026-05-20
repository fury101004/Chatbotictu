from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from functools import lru_cache
from typing import Any

from cachetools import TTLCache

try:
    import redis.asyncio as _redis_module
except Exception:  # pragma: no cover - optional dependency.
    _redis_module = None


class MemoryStore:
    def __init__(
        self,
        *,
        redis_url: str | None = None,
        default_ttl_seconds: int = 3600,
        max_sessions: int = 4096,
    ) -> None:
        self.default_ttl_seconds = default_ttl_seconds
        self._cache: TTLCache[str, list[dict[str, Any]]] = TTLCache(
            maxsize=max_sessions,
            ttl=default_ttl_seconds,
        )
        self._expires_at: dict[str, float] = {}
        self._redis_url = redis_url if redis_url is not None else os.getenv("REDIS_URL", "")
        self._redis = None
        if self._redis_url and _redis_module is not None:
            self._redis = _redis_module.from_url(self._redis_url, decode_responses=True)

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    async def save(self, session_id: str, messages: list[dict], ttl_seconds: int = 3600) -> None:
        key = self._key(session_id)
        normalized = self._normalize_messages(messages)
        ttl = max(1, int(ttl_seconds or self.default_ttl_seconds))

        if self._redis is not None:
            try:
                await self._redis.setex(key, ttl, json.dumps(normalized, ensure_ascii=False))
                return
            except Exception:
                self._redis = None

        self._cache[key] = normalized
        self._expires_at[key] = time.monotonic() + ttl

    async def load(self, session_id: str) -> list[dict]:
        key = self._key(session_id)

        if self._redis is not None:
            try:
                raw = await self._redis.get(key)
                if not raw:
                    return []
                payload = json.loads(raw)
                return self._normalize_messages(payload if isinstance(payload, list) else [])
            except Exception:
                self._redis = None

        expires_at = self._expires_at.get(key)
        if expires_at is not None and expires_at <= time.monotonic():
            await self.delete(session_id)
            return []
        return list(self._cache.get(key, []))

    async def delete(self, session_id: str) -> None:
        key = self._key(session_id)
        if self._redis is not None:
            try:
                await self._redis.delete(key)
            except Exception:
                self._redis = None
        self._cache.pop(key, None)
        self._expires_at.pop(key, None)

    def _key(self, session_id: str) -> str:
        cleaned = str(session_id or "anonymous").strip() or "anonymous"
        return f"chat_memory:{cleaned}"

    def _normalize_messages(self, messages: list[dict]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for item in messages[-60:]:
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "").strip()
            if role and content:
                normalized.append({"role": role, "content": content})
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

