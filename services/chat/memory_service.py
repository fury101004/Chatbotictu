from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
from typing import Any


SESSION_MEMORY: dict[str, deque] = defaultdict(lambda: deque(maxlen=6))


def get_memory_store() -> dict[str, deque]:
    return SESSION_MEMORY


def append_retrieval_memory(
    session_id: str,
    *,
    query: str,
    sources: list[str],
    retrieved_ids: list[str],
    rag_tool: str | None = None,
) -> None:
    SESSION_MEMORY[session_id].append(
        {
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "sources": list(sources),
            "retrieved_ids": list(retrieved_ids),
            "rag_tool": rag_tool,
        }
    )


def clear_memory_store() -> None:
    SESSION_MEMORY.clear()
