from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from services.rag.source_display_service import format_source_label


USER_AUDIENCE = "user"
ADMIN_AUDIENCE = "admin"
USER_EXCERPT_CHARS = 280
ADMIN_EXCERPT_CHARS = 1200
_YEAR_RE = re.compile(r"\b(20\d{2}(?:[-_/]20\d{2})?)\b")
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "system_prompt",
    "token",
)


def _compact_excerpt(value: object, limit: int) -> str:
    compact = " ".join(str(value or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."


def _public_url(metadata: dict[str, Any], source: str) -> str:
    for value in (metadata.get("public_url"), metadata.get("url"), source):
        candidate = str(value or "").strip()
        if candidate.startswith(("https://", "http://")):
            return candidate
    return ""


def _year(metadata: dict[str, Any], source: str) -> str:
    explicit = str(metadata.get("academic_year") or metadata.get("year") or "").strip()
    if explicit:
        return explicit.replace("_", "-").replace("/", "-")
    match = _YEAR_RE.search(source)
    return match.group(1).replace("_", "-").replace("/", "-") if match else ""


def _document_name(metadata: dict[str, Any], source: str) -> str:
    label = format_source_label(source)
    if label:
        return label
    filename = str(metadata.get("file_name") or "").strip()
    return PurePosixPath(filename.replace("\\", "/")).name if filename else "Tài liệu ICTU"


def _safe_admin_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in metadata.items():
        normalized_key = str(key or "").casefold()
        if any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            if isinstance(value, str) and _is_absolute_or_internal_path(value):
                continue
            result[str(key)] = value
        elif isinstance(value, list):
            result[str(key)] = [
                item for item in value
                if isinstance(item, (str, int, float, bool)) or item is None
                if not isinstance(item, str) or not _is_absolute_or_internal_path(item)
            ]
    return result


def _is_absolute_or_internal_path(value: str) -> bool:
    candidate = str(value or "").strip()
    if not candidate or candidate.startswith(("https://", "http://")):
        return False
    return Path(candidate).is_absolute() or re.match(r"^[A-Za-z]:[\\/]", candidate) is not None


def _user_citation(document: str, metadata: dict[str, Any], source: str) -> dict[str, Any]:
    citation: dict[str, Any] = {
        "document_name": _document_name(metadata, source),
    }
    title = str(metadata.get("section_title") or metadata.get("title") or "").strip()
    chapter = str(metadata.get("chapter") or metadata.get("section") or "").strip()
    page_number = metadata.get("page_number")
    year = _year(metadata, source)
    url = _public_url(metadata, source)
    excerpt = _compact_excerpt(document, USER_EXCERPT_CHARS)

    if title:
        citation["title"] = title
    if chapter and chapter != title:
        citation["chapter"] = chapter
    if isinstance(page_number, int) and page_number > 0:
        citation["page_number"] = page_number
    elif str(page_number or "").isdigit() and int(str(page_number)) > 0:
        citation["page_number"] = int(str(page_number))
    if year:
        citation["year"] = year
    if url:
        citation["url"] = url
    if excerpt:
        citation["excerpt"] = excerpt
    return citation


def serialize_citations(
    chunks: Iterable[Any] | None,
    sources: list[str] | None = None,
    *,
    audience: str = USER_AUDIENCE,
) -> list[dict[str, Any]]:
    selected_audience = ADMIN_AUDIENCE if audience == ADMIN_AUDIENCE else USER_AUDIENCE
    citations: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    seen_sources: set[str] = set()

    for chunk in chunks or []:
        metadata = dict(getattr(chunk, "metadata", {}) or {})
        source = str(metadata.get("source") or "").strip()
        if source == "BOT_RULE":
            continue
        if source:
            seen_sources.add(source)
        document = str(getattr(chunk, "document", "") or "")
        user_citation = _user_citation(document, metadata, source)
        key = (
            str(user_citation.get("document_name") or ""),
            str(user_citation.get("title") or ""),
            str(user_citation.get("page_number") or ""),
        )
        if key in seen:
            continue
        seen.add(key)

        if selected_audience == ADMIN_AUDIENCE:
            admin_citation = dict(user_citation)
            if source:
                admin_citation["source"] = source
            source_path = str(metadata.get("source_path") or "").strip()
            if source_path and not _is_absolute_or_internal_path(source_path):
                admin_citation["source_path"] = source_path
            admin_citation["excerpt"] = _compact_excerpt(document, ADMIN_EXCERPT_CHARS)
            admin_citation["metadata"] = _safe_admin_metadata(metadata)
            citations.append(admin_citation)
        else:
            citations.append(user_citation)

    for source in sources or []:
        raw_source = str(source or "").strip()
        if not raw_source or raw_source == "BOT_RULE":
            continue
        if raw_source in seen_sources:
            continue
        user_citation = _user_citation("", {}, raw_source)
        key = (
            str(user_citation.get("document_name") or ""),
            str(user_citation.get("title") or ""),
            str(user_citation.get("page_number") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        if selected_audience == ADMIN_AUDIENCE:
            user_citation["source"] = raw_source
            user_citation["metadata"] = {}
        citations.append(user_citation)

    return citations


def serialize_chat_payload(payload: dict[str, Any], *, audience: str) -> dict[str, Any]:
    result = dict(payload)
    if audience == ADMIN_AUDIENCE:
        result["source_details"] = list(result.pop("_admin_source_details", []) or result.get("source_details") or [])
        return result

    result.pop("sources", None)
    result.pop("_admin_source_details", None)
    result["source_details"] = list(result.get("source_details") or [])
    return result
