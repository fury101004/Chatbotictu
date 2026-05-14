from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Optional


_ACADEMIC_YEAR_RE = re.compile(r"\b(20\d{2})\s*[-/]\s*(20\d{2})\b")
_SINGLE_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_PAGE_PATTERNS = (
    re.compile(r"^(?:trang|page)\s*[:\-]?\s*(\d{1,4})(?:\b|/)", re.IGNORECASE),
    re.compile(r"^\[\s*(?:trang|page)\s*(\d{1,4})\s*\]", re.IGNORECASE),
)
_SENTENCE_END_RE = re.compile(r"[.!?。！？…]+[\"')\]]*$")
_CLAUSE_END_RE = re.compile(r"[,;:，；：]+[\"')\]]*$")


def _detect_chunk_type(text: str) -> str:
    if "```" in text:
        return "code"
    if any(char in text for char in ["│", "┃", "├", "┣", "┳", "═"]):
        return "table"
    if re.search(r"^[-*•]\s", text, re.M):
        return "list"
    return "text"


def _find_sentence_boundary(words: list[str], start: int, hard_end: int, max_words: int) -> int:
    """Tìm điểm cắt tốt nhất: cuối câu (.!?) > dấu phẩy (,;:) > word boundary."""
    if hard_end >= len(words):
        return hard_end

    minimum_end = start + max(1, int(max_words * 0.6))

    # Ưu tiên 1: dấu kết câu (. ! ? …)
    for index in range(hard_end - 1, minimum_end - 1, -1):
        if _SENTENCE_END_RE.search(words[index]):
            return index + 1

    # Ưu tiên 2: dấu phân cách mệnh đề (, ; :) — tránh cắt giữa câu dài
    for index in range(hard_end - 1, minimum_end - 1, -1):
        if _CLAUSE_END_RE.search(words[index]):
            return index + 1

    # Ưu tiên 3: cắt tại hard_end (luôn là word boundary)
    return hard_end


def _split_text_windows(text: str, max_words: int, overlap_words: int) -> list[str]:
    words = text.split()
    if not words:
        return []

    if max_words <= 0 or len(words) <= max_words:
        return [text.strip()]

    overlap_words = max(0, min(overlap_words, max_words - 1))
    windows: list[str] = []
    start = 0

    while start < len(words):
        hard_end = min(start + max_words, len(words))
        end = _find_sentence_boundary(words, start, hard_end, max_words)
        window = " ".join(words[start:end]).strip()
        if window:
            windows.append(window)
        if end >= len(words):
            break
        start = max(start + 1, end - overlap_words)

    return windows


def _tail_overlap_text(text: str, overlap_words: int) -> str:
    if overlap_words <= 0:
        return ""
    words = text.split()
    if not words:
        return ""
    return " ".join(words[-overlap_words:]).strip()


def _extract_page_number(line: str) -> Optional[int]:
    candidate = line.strip()
    if not candidate:
        return None

    for pattern in _PAGE_PATTERNS:
        match = pattern.search(candidate)
        if match:
            try:
                return int(match.group(1))
            except (TypeError, ValueError):
                return None
    return None


def extract_academic_year(source_name: str, filename: str, content: str) -> Optional[str]:
    combined = f"{source_name}\n{filename}\n{content[:8000]}"
    matches = [
        (int(match.group(1)), int(match.group(2)))
        for match in _ACADEMIC_YEAR_RE.finditer(combined)
    ]
    if matches:
        start, end = max(matches, key=lambda pair: (pair[1], pair[0]))
        return f"{start}-{end}"

    years = sorted({int(match.group(1)) for match in _SINGLE_YEAR_RE.finditer(combined)})
    if len(years) >= 2:
        for index in range(len(years) - 1, 0, -1):
            prev_year = years[index - 1]
            current_year = years[index]
            if current_year - prev_year == 1:
                return f"{prev_year}-{current_year}"
    return None


def infer_document_type(source_name: str, filename: str, tool_name: Optional[str], content: str) -> str:
    haystack = f"{source_name} {filename}".casefold()
    content_lower = content.casefold()

    if haystack.endswith(".questions.md") or "**question:**" in content_lower or "**q:**" in content_lower:
        return "qa_pair"
    if tool_name == "student_handbook_rag":
        return "student_handbook"
    if tool_name == "school_policy_rag":
        return "school_policy"
    if tool_name == "student_faq_rag":
        return "student_faq"

    if any(keyword in haystack for keyword in ["quyet dinh", "quy dinh", "quy che", "thong tu", "nghi dinh", "luat"]):
        return "policy_document"
    if any(keyword in haystack for keyword in ["so tay", "handbook", "cam nang"]):
        return "handbook_document"
    return "general_document"


def smart_chunk(
    content: str,
    filename: str,
    *,
    source_name: Optional[str],
    chunk_size: int,
    chunk_overlap: int,
    count_tokens_fn: Callable[[str], int],
) -> list[dict[str, Any]]:
    lines = content.split("\n")
    max_words = max(1, int(chunk_size or 1000))
    overlap_words = max(0, int(chunk_overlap or 0))
    overlap_words = min(overlap_words, max_words - 1) if max_words > 1 else 0

    chunks: list[dict[str, Any]] = []
    buffer: list[str] = []
    buffer_word_count = 0
    default_title = Path(source_name or filename).stem
    current_title = default_title
    current_level = 1
    current_chapter = default_title
    current_section = default_title
    current_page_number: Optional[int] = None
    heading_stack: dict[int, str] = {1: default_title}
    in_code_block = False
    buffer_is_overlap_seed = False

    def flush_buffer(*, preserve_overlap: bool = False) -> None:
        nonlocal buffer, buffer_word_count, buffer_is_overlap_seed
        if not buffer:
            return

        text = "\n".join(buffer).strip()
        if not text:
            buffer.clear()
            buffer_word_count = 0
            buffer_is_overlap_seed = False
            return

        if buffer_is_overlap_seed and not preserve_overlap:
            buffer.clear()
            buffer_word_count = 0
            buffer_is_overlap_seed = False
            return

        chunk_type = _detect_chunk_type(text)
        if chunk_type in {"code", "table"}:
            segments = [text]
        else:
            segments = _split_text_windows(
                text,
                max_words=max_words,
                overlap_words=overlap_words if preserve_overlap else 0,
            )

        for segment in segments:
            chunks.append(
                {
                    "text": segment,
                    "title": current_title,
                    "level": current_level,
                    "chapter": current_chapter,
                    "section": current_section,
                    "page_number": current_page_number,
                    "token_count": count_tokens_fn(segment),
                    "word_count": len(segment.split()),
                    "type": chunk_type,
                }
            )

        if preserve_overlap and overlap_words > 0 and chunk_type not in {"code", "table"}:
            overlap_text = _tail_overlap_text(text, overlap_words)
            buffer = [overlap_text] if overlap_text else []
            buffer_word_count = len(overlap_text.split()) if overlap_text else 0
            buffer_is_overlap_seed = bool(overlap_text)
        else:
            buffer.clear()
            buffer_word_count = 0
            buffer_is_overlap_seed = False

    for line in lines:
        line = line.rstrip()
        detected_page_number = _extract_page_number(line)
        if detected_page_number is not None:
            current_page_number = detected_page_number

        if line.startswith("```"):
            in_code_block = not in_code_block

        if re.match(r"^#{1,4}\s", line):
            flush_buffer()
            heading_level = len(line) - len(line.lstrip("#"))
            current_title = line.lstrip("# ").strip() or f"Heading cap {heading_level}"
            current_level = heading_level

            heading_stack[heading_level] = current_title
            for level in list(heading_stack):
                if level > heading_level:
                    del heading_stack[level]
            current_chapter = heading_stack.get(1) or heading_stack.get(2) or default_title
            current_section = " > ".join(heading_stack[level] for level in sorted(heading_stack))

        buffer.append(line)
        buffer_word_count += len(line.split())
        if buffer_is_overlap_seed and len(buffer) > 1:
            buffer_is_overlap_seed = False

        if buffer_word_count > max_words and not in_code_block:
            flush_buffer(preserve_overlap=True)

    flush_buffer()
    return chunks
