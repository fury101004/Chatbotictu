"""
services/chat/context_compressor.py
====================================
Nén context khi nhiều chunk cùng source/academic_year được chọn.
Giảm trùng lặp, giảm token, tăng chất lượng answer.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Optional


_WHITESPACE_RE = re.compile(r"\s+")

# Ngưỡng: nếu > MAX_CHUNKS_SAME_SOURCE chunk từ cùng 1 source → nén
MAX_CHUNKS_SAME_SOURCE = 3
# Tỷ lệ trùng lặp tối thiểu để coi là duplicate
DEDUP_SIMILARITY_THRESHOLD = 0.7
# Giới hạn ký tự cho mỗi nhóm source sau khi nén
MAX_CHARS_PER_SOURCE_GROUP = 4000


def _normalize_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", str(text or "").strip()).casefold()


def _shingle_set(text: str, n: int = 3) -> set[str]:
    """Tạo tập n-gram ký tự để so sánh nhanh mức độ trùng lặp."""
    normalized = _normalize_text(text)
    if len(normalized) < n:
        return {normalized}
    return {normalized[i : i + n] for i in range(len(normalized) - n + 1)}


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def deduplicate_chunks(chunks: list[str], threshold: float = DEDUP_SIMILARITY_THRESHOLD) -> list[str]:
    """Loại bỏ các chunk gần giống nhau (Jaccard similarity > threshold)."""
    if len(chunks) <= 1:
        return chunks

    unique: list[str] = []
    shingle_cache: list[set[str]] = []

    for chunk in chunks:
        chunk_shingles = _shingle_set(chunk)
        is_duplicate = False

        for existing_shingles in shingle_cache:
            if _jaccard_similarity(chunk_shingles, existing_shingles) > threshold:
                is_duplicate = True
                break

        if not is_duplicate:
            unique.append(chunk)
            shingle_cache.append(chunk_shingles)

    return unique


def compress_context(
    context_text: str,
    sources: list[str],
    metadatas: Optional[list[dict]] = None,
    *,
    max_chunks_per_source: int = MAX_CHUNKS_SAME_SOURCE,
    max_chars_per_group: int = MAX_CHARS_PER_SOURCE_GROUP,
) -> str:
    """Nén context: gộp chunk cùng source, dedup, cắt giới hạn.

    Args:
        context_text: Toàn bộ context text (đã ghép từ các chunk)
        sources: Danh sách source tương ứng với từng phần context
        metadatas: Metadata tùy chọn cho từng chunk
        max_chunks_per_source: Ngưỡng kích hoạt nén (default 3)
        max_chars_per_group: Giới hạn ký tự mỗi nhóm source

    Returns:
        Context đã nén, giảm trùng lặp
    """
    if not context_text or not context_text.strip():
        return context_text

    # Tách context thành các đoạn dựa trên marker [source] hoặc metadata
    segments = _split_context_segments(context_text, sources, metadatas)
    if not segments:
        return context_text

    # Nhóm theo source
    grouped: dict[str, list[str]] = defaultdict(list)
    source_order: list[str] = []
    for source, text in segments:
        if source not in grouped:
            source_order.append(source)
        grouped[source].append(text)

    compressed_parts: list[str] = []
    for source in source_order:
        chunks = grouped[source]

        if len(chunks) > max_chunks_per_source:
            # Nén: dedup + cắt giới hạn
            deduped = deduplicate_chunks(chunks)
            merged = "\n\n".join(deduped)
            if len(merged) > max_chars_per_group:
                merged = merged[:max_chars_per_group].rstrip() + "\n[...đã tóm tắt...]"
            compressed_parts.append(f"[Nguồn: {source}]\n{merged}")
        else:
            # Giữ nguyên
            for chunk in chunks:
                compressed_parts.append(chunk)

    return "\n\n".join(compressed_parts).strip()


def _split_context_segments(
    context_text: str,
    sources: list[str],
    metadatas: Optional[list[dict]] = None,
) -> list[tuple[str, str]]:
    """Tách context thành các (source, text) segments."""
    # Thử tách bằng marker pattern [source: ...] hoặc [Nguồn: ...]
    marker_re = re.compile(
        r"^\[(?:source|nguồn|Nguồn|SOURCE)[:\s]+(.+?)\]",
        re.MULTILINE | re.IGNORECASE,
    )

    markers = list(marker_re.finditer(context_text))
    if markers:
        segments: list[tuple[str, str]] = []
        for i, match in enumerate(markers):
            source = match.group(1).strip()
            start = match.end()
            end = markers[i + 1].start() if i + 1 < len(markers) else len(context_text)
            text = context_text[start:end].strip()
            if text:
                segments.append((source, text))
        return segments

    # Fallback: dùng danh sách sources (nếu có) và chia đều context
    if sources:
        lines = context_text.split("\n\n")
        segments = []
        for i, block in enumerate(lines):
            source = sources[i] if i < len(sources) else sources[-1] if sources else "unknown"
            if block.strip():
                segments.append((source, block.strip()))
        return segments

    # Không tách được — trả về nguyên khối
    return [("unknown", context_text)]
