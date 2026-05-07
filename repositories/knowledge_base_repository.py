from __future__ import annotations

from config.db import (
    get_approved_chat_entry_ids as _get_approved_chat_entry_ids,
    get_approved_chat_qas as _get_approved_chat_qas,
    upsert_approved_chat_qa as _upsert_approved_chat_qa,
)


def list_approved_chat_entry_ids() -> set[str]:
    return _get_approved_chat_entry_ids()


def list_approved_chat_qas() -> list[dict[str, str]]:
    return _get_approved_chat_qas()


def save_approved_chat_qa(
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
    _upsert_approved_chat_qa(
        entry_id=entry_id,
        question_row_id=question_row_id,
        answer_row_id=answer_row_id,
        session_id=session_id,
        tool_name=tool_name,
        question=question,
        answer=answer,
        source_name=source_name,
        storage_path=storage_path,
    )
