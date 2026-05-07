from __future__ import annotations

from functools import lru_cache

import tiktoken


@lru_cache(maxsize=1)
def _get_encoding():
    return tiktoken.get_encoding("cl100k_base")


def count_text_tokens(text: str) -> int:
    try:
        encoding = _get_encoding()
    except (MemoryError, OSError):
        return max(1, len(str(text or "").split()))
    return len(encoding.encode(str(text or "")))
