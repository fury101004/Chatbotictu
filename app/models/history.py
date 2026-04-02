"""Persistence helpers for chat history."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, Iterator, List

from app.core.config import DB_NAME


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    DB_NAME.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_NAME, timeout=30)
    try:
        yield connection
    finally:
        connection.close()


def init_db() -> None:
    with _connect() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                user_message TEXT NOT NULL,
                bot_reply TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )
        connection.commit()


def save_chat(user_id: str, user_message: str, bot_reply: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with _connect() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO history (user_id, user_message, bot_reply, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, user_message, bot_reply, timestamp),
        )
        connection.commit()


def get_history_by_user(user_id: str, *, descending: bool = True) -> List[Dict[str, str]]:
    order = "DESC" if descending else "ASC"

    with _connect() as connection:
        cursor = connection.cursor()
        cursor.execute(
            f"""
            SELECT user_message, bot_reply, timestamp
            FROM history
            WHERE user_id = ?
            ORDER BY id {order}
            """,
            (user_id,),
        )
        rows = cursor.fetchall()

    return [
        {
            "question": question,
            "answer": answer,
            "timestamp": timestamp,
        }
        for question, answer, timestamp in rows
    ]


def clear_history(user_id: str) -> None:
    with _connect() as connection:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
        connection.commit()
