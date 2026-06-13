from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
import re
from typing import Any


SESSION_MEMORY: dict[str, deque] = defaultdict(lambda: deque(maxlen=6))
_SOURCE_YEAR_RANGE_RE = re.compile(r"\b(20\d{2})\s*[-_/]\s*(20\d{2})\b")


def get_memory_store() -> dict[str, deque]:
    return SESSION_MEMORY


def extract_source_years(sources: list[str]) -> list[str]:
    years: list[str] = []
    seen: set[str] = set()
    for source in sources:
        for match in _SOURCE_YEAR_RANGE_RE.finditer(str(source or "")):
            year_range = f"{match.group(1)}-{match.group(2)}"
            if year_range not in seen:
                seen.add(year_range)
                years.append(year_range)
    return years


def get_last_retrieval_years(
    session_id: str,
    persistent_memory: list[dict[str, Any]] | None = None,
) -> list[str]:
    history = SESSION_MEMORY.get(session_id)
    if history:
        for item in reversed(history):
            years = extract_source_years(list(item.get("sources") or []))
            if years:
                return years

    for item in reversed(list(persistent_memory or [])):
        years = extract_source_years(list(item.get("sources") or []))
        if years:
            return years
    return []


def append_retrieval_memory(
    session_id: str,
    *,
    query: str,
    original_question: str = "",
    rewritten_question: str = "",
    sources: list[str],
    retrieved_ids: list[str],
    rag_tool: str | None = None,
) -> None:
    SESSION_MEMORY[session_id].append(
        {
            "query": query,
            "original_question": original_question or query,
            "rewritten_question": rewritten_question or query,
            "timestamp": datetime.now().isoformat(),
            "sources": list(sources),
            "retrieved_ids": list(retrieved_ids),
            "rag_tool": rag_tool,
        }
    )


def clear_memory_store() -> None:
    SESSION_MEMORY.clear()
