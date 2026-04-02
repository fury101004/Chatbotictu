from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import unicodedata
from pathlib import Path
from typing import List, Sequence, Tuple

from app.data.source_routes import SOURCE_ROUTES, route_matches_relative_path
from app.core.config import CLEAN_MD_DIR, RAG_MD_DIR


IGNORE_DIRS = {".venv", "__pycache__", ".git"}

PAGE_HEADING_RE = re.compile(r"^\s*##\s*Trang\s+\d+\s*$", re.IGNORECASE)
PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,4}\s*$")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _split_frontmatter(markdown: str) -> Tuple[str, str]:
    if markdown.startswith("---"):
        parts = markdown.split("---", 2)
        if len(parts) >= 3:
            frontmatter = "---" + parts[1] + "---\n\n"
            body = parts[2].lstrip()
            return frontmatter, body
    return "", markdown


def _extract_year(text: str) -> str:
    match = re.search(r"\b(20\d{2})\b", text)
    return match.group(1) if match else ""


def _normalize_lookup_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", normalized).strip().lower()


def _frontmatter_has_key(frontmatter: str, key: str) -> bool:
    return bool(re.search(rf"^\s*{re.escape(key)}\s*:", frontmatter, flags=re.MULTILINE))


def _inject_frontmatter_key(frontmatter: str, key: str, value: str) -> str:
    if not frontmatter.startswith("---") or _frontmatter_has_key(frontmatter, key):
        return frontmatter

    parts = frontmatter.split("---", 2)
    if len(parts) < 3:
        return frontmatter

    meta = parts[1].strip("\n")
    meta = meta + f'\n{key}: "{value}"\n'
    return "---\n" + meta.strip("\n") + "\n---\n\n"


def _is_noise_line(line: str) -> bool:
    stripped = line.strip()
    normalized = _normalize_lookup_text(stripped)
    if not stripped:
        return True
    if PAGE_HEADING_RE.match(stripped):
        return True
    if normalized in {"muc luc", "noi dung"}:
        return True
    if PAGE_NUMBER_RE.match(stripped):
        return True
    if " trang" in normalized and len(stripped) < 60:
        return True
    return False


def _normalize_lines(body: str) -> List[str]:
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output: List[str] = []
    blank_count = 0

    for line in lines:
        candidate = line.rstrip()
        if _is_noise_line(candidate):
            blank_count += 1
            if blank_count <= 1:
                output.append("")
            continue
        blank_count = 0
        output.append(candidate.strip())

    collapsed: List[str] = []
    previous_blank = False
    for line in output:
        is_blank = line.strip() == ""
        if is_blank and previous_blank:
            continue
        collapsed.append("" if is_blank else line)
        previous_blank = is_blank

    while collapsed and collapsed[0] == "":
        collapsed.pop(0)
    while collapsed and collapsed[-1] == "":
        collapsed.pop()
    return collapsed


def _sections_from_markdown(lines: Sequence[str]) -> List[Tuple[str, List[str]]]:
    sections: List[Tuple[str, List[str]]] = []
    current_title = "Noi dung"
    current_lines: List[str] = []
    heading_re = re.compile(r"^\s*(#{1,3})\s+(.+?)\s*$")

    for line in lines:
        match = heading_re.match(line)
        if match:
            if current_lines:
                sections.append((current_title, current_lines))
            current_title = match.group(2).strip()
            current_lines = [line]
            continue
        current_lines.append(line)

    if current_lines:
        sections.append((current_title, current_lines))
    return sections


def _chunk_section(lines: Sequence[str], max_chars: int = 1800, min_chars: int = 500) -> List[str]:
    text = "\n".join(lines).strip()
    if len(text) <= max_chars:
        return [text] if text else []

    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    chunks: List[str] = []
    buffer: List[str] = []
    buffer_length = 0

    def flush() -> None:
        nonlocal buffer, buffer_length
        if buffer:
            chunks.append("\n\n".join(buffer).strip())
            buffer = []
            buffer_length = 0

    for paragraph in paragraphs:
        paragraph_length = len(paragraph) + (2 if buffer else 0)
        if buffer_length + paragraph_length > max_chars and buffer_length >= min_chars:
            flush()
        buffer.append(paragraph)
        buffer_length += paragraph_length

    flush()
    return chunks


def prepare_one_file(src_path: Path, dst_path: Path) -> None:
    raw_text = _read_text(src_path)
    frontmatter, body = _split_frontmatter(raw_text)

    year = _extract_year(str(src_path)) or _extract_year(body[:2000])
    if frontmatter and year:
        frontmatter = _inject_frontmatter_key(frontmatter, "year", year)

    lines = _normalize_lines(body)
    sections = _sections_from_markdown(lines)

    output_parts: List[str] = []
    if frontmatter:
        output_parts.append(frontmatter.strip())
        output_parts.append("")

    chunk_index = 1
    for title, section_lines in sections:
        for chunk_text in _chunk_section(section_lines):
            if not chunk_text.strip():
                continue
            output_parts.append(f"## Chunk {chunk_index}: {title}")
            output_parts.append("")
            output_parts.append(chunk_text.strip())
            output_parts.append("")
            chunk_index += 1

    content = "\n".join(output_parts).strip() + "\n"
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_text(content, encoding="utf-8")


def _prune_empty_dirs(root: Path) -> None:
    for directory in sorted(root.rglob("*"), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()


def _clear_matching_output(route: str) -> None:
    out_root = Path(RAG_MD_DIR)
    if not out_root.exists():
        return

    if route == "all":
        for child in out_root.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
        return

    for path in sorted(out_root.rglob("*.md")):
        rel_path = path.relative_to(out_root)
        if route_matches_relative_path(rel_path, route):
            path.unlink()

    _prune_empty_dirs(out_root)


def build_rag_markdown(route: str = "all") -> dict:
    route = route.strip().lower()
    if route not in SOURCE_ROUTES:
        raise ValueError(f"Unsupported route: {route}")

    in_root = Path(CLEAN_MD_DIR)
    out_root = Path(RAG_MD_DIR)
    if not in_root.exists():
        raise FileNotFoundError(f"CLEAN_MD_DIR does not exist: {in_root}")

    _clear_matching_output(route)

    processed = 0
    for dirpath, dirnames, filenames in os.walk(in_root):
        dirnames[:] = [name for name in dirnames if name not in IGNORE_DIRS and not name.startswith(".")]
        for filename in filenames:
            if not filename.lower().endswith(".md"):
                continue

            src_path = Path(dirpath) / filename
            rel_path = src_path.relative_to(in_root)
            if not route_matches_relative_path(rel_path, route):
                continue

            dst_path = out_root / rel_path
            prepare_one_file(src_path, dst_path)
            processed += 1
            if processed % 50 == 0:
                print(f"... processed {processed} markdown files for route={route}")

    report = {
        "route": route,
        "processed": processed,
        "input_root": str(in_root),
        "output_root": str(out_root),
    }
    report_path = out_root / "_reports" / f"{route}_rag_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert clean markdown into chunk-friendly RAG markdown.")
    parser.add_argument(
        "--route",
        choices=SOURCE_ROUTES,
        default="all",
        help="Rebuild only handbook, only policy, or all RAG markdown.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        report = build_rag_markdown(route=args.route)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    print(
        f"Done preparing rag markdown for route={report['route']}. "
        f"Files processed: {report['processed']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
