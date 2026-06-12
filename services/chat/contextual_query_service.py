from __future__ import annotations

import re
from typing import Iterable

from services.rag.ictu_scope_service import normalize_scope_text


_YEAR_RANGE_RE = re.compile(r"\b(20\d{2})\s*[-/]\s*(20\d{2})\b")
_FOLLOW_UP_PREFIXES = (
    "còn",
    "thế còn",
    "vậy còn",
    "vậy",
    "thế",
)
_FOLLOW_UP_SUFFIXES = (
    "thì sao",
    "thế nào",
    "thì thế nào",
    "sao",
)
_ACADEMIC_FOLLOW_UP_MARKERS = (
    "khoa",
    "nam hoc",
    "nganh",
    "tin chi",
    "tot nghiep",
    "chung chi",
    "ngoai ngu",
    "diem ren luyen",
    "hoc bong",
    "hoc phi",
    "sinh vien",
)
_NORMALIZED_FOLLOW_UP_PREFIXES = tuple(normalize_scope_text(prefix) for prefix in _FOLLOW_UP_PREFIXES)
_NORMALIZED_FOLLOW_UP_SUFFIXES = tuple(normalize_scope_text(suffix) for suffix in _FOLLOW_UP_SUFFIXES)


def _has_academic_follow_up_signal(question: str, normalized: str) -> bool:
    return bool(_YEAR_RANGE_RE.search(question)) or any(
        marker in normalized for marker in _ACADEMIC_FOLLOW_UP_MARKERS
    )


def _capitalize_question(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return ""
    cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned if cleaned.endswith("?") else f"{cleaned.rstrip('.!')}?"


def _last_user_question(history: Iterable[dict[str, str]]) -> str:
    for item in reversed(list(history)):
        if str(item.get("role") or "").strip().casefold() != "user":
            continue
        content = str(item.get("rewritten_question") or item.get("content") or "").strip()
        if content:
            return content
    return ""


def is_contextual_follow_up(question: str) -> bool:
    normalized = normalize_scope_text(question)
    if not normalized:
        return False

    has_academic_signal = _has_academic_follow_up_signal(question, normalized)
    if any(normalized == prefix for prefix in _NORMALIZED_FOLLOW_UP_PREFIXES):
        return True
    if has_academic_signal and any(
        normalized.startswith(f"{prefix} ") for prefix in _NORMALIZED_FOLLOW_UP_PREFIXES
    ):
        return True
    if has_academic_signal and any(
        normalized == suffix or normalized.endswith(f" {suffix}") for suffix in _NORMALIZED_FOLLOW_UP_SUFFIXES
    ):
        return True
    return len(normalized.split()) <= 3 and has_academic_signal


def _extract_follow_up_topic(question: str) -> str:
    cleaned = re.sub(r"[?!.]+$", "", str(question or "").strip())
    normalized = normalize_scope_text(cleaned)

    for prefix in _FOLLOW_UP_PREFIXES:
        normalized_prefix = normalize_scope_text(prefix)
        if normalized == normalized_prefix:
            return ""
        if normalized.startswith(f"{normalized_prefix} "):
            words_to_remove = len(normalized_prefix.split())
            cleaned = " ".join(cleaned.split()[words_to_remove:]).strip()
            normalized = normalize_scope_text(cleaned)
            break

    for suffix in _FOLLOW_UP_SUFFIXES:
        normalized_suffix = normalize_scope_text(suffix)
        if normalized == normalized_suffix:
            return ""
        if normalized.endswith(f" {normalized_suffix}"):
            words_to_remove = len(normalized_suffix.split())
            cleaned = " ".join(cleaned.split()[:-words_to_remove]).strip()
            break

    return cleaned.strip(" ,;:-")


def _next_year_range(previous_question: str) -> str:
    match = _YEAR_RANGE_RE.search(previous_question)
    if not match:
        return ""
    return f"{int(match.group(1)) + 1}-{int(match.group(2)) + 1}"


def _rewrite_year_follow_up(previous_question: str, current_question: str) -> str:
    current_year = _YEAR_RANGE_RE.search(current_question)
    replacement = current_year.group(0).replace("/", "-") if current_year else ""
    normalized_current = normalize_scope_text(current_question)
    if not replacement and ("khoa sau" in normalized_current or "nam hoc sau" in normalized_current):
        replacement = _next_year_range(previous_question)
    if not replacement or not _YEAR_RANGE_RE.search(previous_question):
        return ""

    rewritten = _YEAR_RANGE_RE.sub(replacement, previous_question, count=1)
    return _capitalize_question(rewritten)


def rewrite_follow_up_question(previous_question: str, current_question: str) -> str:
    previous = str(previous_question or "").strip()
    current = str(current_question or "").strip()
    if not previous or not current or not is_contextual_follow_up(current):
        return current

    year_rewrite = _rewrite_year_follow_up(previous, current)
    if year_rewrite:
        return year_rewrite

    normalized_previous = normalize_scope_text(previous)
    normalized_current = normalize_scope_text(current)

    if "chung chi ngoai ngu" in normalized_current and "tot nghiep" in normalized_previous:
        suffix = " của sinh viên ICTU" if "sinh vien ictu" in normalized_previous else ""
        return _capitalize_question(f"Điều kiện chứng chỉ ngoại ngữ để tốt nghiệp{suffix} là gì")

    if "diem ren luyen" in normalized_current and "hoc bong" in normalized_previous:
        return "Điểm rèn luyện cần đạt điều kiện gì để xét học bổng?"

    topic = _extract_follow_up_topic(current)
    if not topic:
        return current

    normalized_topic = normalize_scope_text(topic)
    if normalized_topic.startswith("nganh "):
        return _capitalize_question(f"Đối với {topic}, {previous[0].lower() + previous[1:].rstrip('?')}")

    return _capitalize_question(f"Về {topic}, {previous[0].lower() + previous[1:].rstrip('?')}")


def rewrite_contextual_question(question: str, history: Iterable[dict[str, str]]) -> str:
    previous_question = _last_user_question(history)
    return rewrite_follow_up_question(previous_question, question)
