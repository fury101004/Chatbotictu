from __future__ import annotations

import re
from pathlib import PurePosixPath


_HANDBOOK_RE = re.compile(
    r"(?:^|/)(?:\d+\.\s*)?SO TAY SINH VIEN (?P<year>20\d{2}[-_]20\d{2})(?P<questions>\.questions)?\.md$",
    flags=re.IGNORECASE,
)


def format_source_label(source: str) -> str:
    raw_source = str(source or "").strip()
    if not raw_source:
        return ""

    normalized = raw_source.replace("\\", "/")
    if normalized.startswith(("http://", "https://")):
        return normalized

    handbook_match = _HANDBOOK_RE.search(normalized)
    if handbook_match:
        year = handbook_match.group("year").replace("_", "-")
        if handbook_match.group("questions"):
            return f"Sổ tay sinh viên {year} (hỏi đáp trích xuất)"
        return f"Sổ tay sinh viên {year} (bản đầy đủ)"

    name = PurePosixPath(normalized).name or normalized
    if name.casefold().endswith(".questions.md"):
        return f"{name[:-13]} (hỏi đáp trích xuất)"
    return name


def build_source_details(sources: list[str] | None) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    seen: set[str] = set()
    for source in sources or []:
        raw_source = str(source or "").strip()
        if not raw_source or raw_source == "BOT_RULE" or raw_source in seen:
            continue
        seen.add(raw_source)
        details.append({"source": raw_source, "label": format_source_label(raw_source) or raw_source})
    return details
