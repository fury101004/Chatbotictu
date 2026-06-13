from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.memory_store import MemoryStore, stable_session_id


class MemoryStoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "memory.db"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_save_load_and_delete_with_sqlite_backend(self) -> None:
        store = MemoryStore(db_path=self.db_path)
        messages = [{"role": "user", "content": "Xin chao"}]

        await store.save("session-1", messages, ttl_seconds=60)
        self.assertEqual(store.backend, "sqlite")
        self.assertEqual(await store.load("session-1"), messages)

        await store.delete("session-1")
        self.assertEqual(await store.load("session-1"), [])

    async def test_ttl_expiry_removes_old_memory(self) -> None:
        store = MemoryStore(db_path=self.db_path)
        await store.save("session-ttl", [{"role": "user", "content": "A"}], ttl_seconds=1)

        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE chat_memory SET expires_at = 0")
        conn.commit()
        conn.close()

        self.assertEqual(await store.load("session-ttl"), [])

    async def test_memory_persists_across_store_instances(self) -> None:
        first_store = MemoryStore(db_path=self.db_path)
        await first_store.save(
            "session",
            [
                {
                    "role": "model",
                    "content": "persistent",
                    "sources": ["student_handbooks/8. SO TAY SINH VIEN 2025-2026.md"],
                }
            ],
        )

        second_store = MemoryStore(db_path=self.db_path)
        self.assertEqual(
            await second_store.load("session"),
            [
                {
                    "role": "model",
                    "content": "persistent",
                    "sources": ["student_handbooks/8. SO TAY SINH VIEN 2025-2026.md"],
                }
            ],
        )

    async def test_memory_limits_messages_and_sessions(self) -> None:
        store = MemoryStore(db_path=self.db_path, max_messages=2, max_sessions=2)
        await store.save(
            "session-1",
            [
                {"role": "user", "content": "one"},
                {"role": "model", "content": "two"},
                {"role": "user", "content": "three"},
            ],
        )
        await store.save("session-2", [{"role": "user", "content": "two"}])
        await store.save("session-3", [{"role": "user", "content": "three"}])

        self.assertEqual(
            await store.load("session-1"),
            [],
        )
        self.assertEqual(
            await store.load("session-3"),
            [{"role": "user", "content": "three"}],
        )

    def test_stable_session_id_hashes_user_or_cookie_identifier(self) -> None:
        self.assertEqual(stable_session_id(user_id="u1"), stable_session_id(user_id="u1"))
        self.assertEqual(stable_session_id(anonymous_id="cookie"), stable_session_id(anonymous_id="cookie"))
        self.assertNotEqual(stable_session_id(user_id="u1"), stable_session_id(user_id="u2"))


if __name__ == "__main__":
    unittest.main()
