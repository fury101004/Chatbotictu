from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from services.memory_store import MemoryStore, stable_session_id


class MemoryStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_save_load_and_delete_with_memory_backend(self) -> None:
        store = MemoryStore(redis_url="")
        messages = [{"role": "user", "content": "Xin chao"}]

        await store.save("session-1", messages, ttl_seconds=60)
        self.assertEqual(await store.load("session-1"), messages)

        await store.delete("session-1")
        self.assertEqual(await store.load("session-1"), [])

    async def test_ttl_expiry_removes_old_memory(self) -> None:
        store = MemoryStore(redis_url="")
        await store.save("session-ttl", [{"role": "user", "content": "A"}], ttl_seconds=1)

        store._expires_at[store._key("session-ttl")] = 0
        await asyncio.sleep(0)

        self.assertEqual(await store.load("session-ttl"), [])

    async def test_redis_fallback_when_client_is_unavailable(self) -> None:
        with patch("services.memory_store._redis_module", None):
            store = MemoryStore(redis_url="redis://localhost:6379/0")

        self.assertEqual(store.backend, "memory")
        await store.save("session", [{"role": "user", "content": "fallback"}])
        self.assertEqual((await store.load("session"))[0]["content"], "fallback")

    def test_stable_session_id_hashes_user_or_cookie_identifier(self) -> None:
        self.assertEqual(stable_session_id(user_id="u1"), stable_session_id(user_id="u1"))
        self.assertEqual(stable_session_id(anonymous_id="cookie"), stable_session_id(anonymous_id="cookie"))
        self.assertNotEqual(stable_session_id(user_id="u1"), stable_session_id(user_id="u2"))


if __name__ == "__main__":
    unittest.main()

