from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import config.db as db
import config.middleware as middleware


class ChatHistorySchemaTests(unittest.TestCase):
    def test_init_db_migrates_chat_history_to_include_session_id(self) -> None:
        with tempfile.TemporaryDirectory(dir="E:\\new-test") as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "bot_config.db"
            prompt_path = temp_root / "systemprompt.md"

            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT,
                    content TEXT,
                    timestamp TEXT DEFAULT (datetime('now', 'localtime'))
                )
                """
            )
            conn.execute(
                "INSERT INTO chat_history (role, content) VALUES (?, ?)",
                ("user", "Xin chao"),
            )
            conn.commit()
            conn.close()

            with (
                patch("config.db.DB_PATH", db_path),
                patch("config.db.SYSTEM_PROMPT_PATH", prompt_path),
            ):
                db.init_db()

                conn = sqlite3.connect(db_path)
                columns = [row[1] for row in conn.execute("PRAGMA table_info(chat_history)").fetchall()]
                row = conn.execute(
                    "SELECT role, content, session_id FROM chat_history ORDER BY id ASC"
                ).fetchone()
                indexes = [row[1] for row in conn.execute("PRAGMA index_list(chat_history)").fetchall()]
                conn.close()

            self.assertIn("session_id", columns)
            self.assertEqual(row, ("user", "Xin chao", "default"))
            self.assertIn("idx_chat_history_session_id_id", indexes)


class MiddlewareConfigTests(unittest.TestCase):
    def test_register_middleware_uses_stable_session_secret(self) -> None:
        app = Mock()

        with patch.object(middleware.settings, "SESSION_SECRET", "stable-session-secret"):
            middleware.register_middleware(app)

        app.add_middleware.assert_any_call(
            middleware.SessionMiddleware,
            secret_key="stable-session-secret",
        )


if __name__ == "__main__":
    unittest.main()
