from __future__ import annotations

"""Deprecated compatibility shim for legacy imports.

Use `shared.text_utils` for normalization/tokenization helpers.
This module remains only to avoid breaking external imports during the
incremental refactor.
"""

from config.settings import settings


def split_text(text: str, chunk_size=None, chunk_overlap=None):
    words = str(text or "").split()
    size = chunk_size or settings.CHUNK_SIZE
    overlap = chunk_overlap or settings.CHUNK_OVERLAP
    chunks = []
    index = 0
    while index < len(words):
        chunks.append(" ".join(words[index : index + size]))
        index += max(1, size - overlap)
    return chunks or [""]


def assign_level(word_count: int) -> int:
    if word_count < 100:
        return 1
    if word_count < 300:
        return 2
    if word_count < 600:
        return 3
    if word_count < 1000:
        return 4
    return 5
