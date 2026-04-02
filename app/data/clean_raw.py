from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from PyPDF2 import PdfReader
from docx import Document

from app.core.config import CLEAN_MD_DIR, RAW_DATA_DIR
from app.data.source_routes import SOURCE_ROUTES, route_matches_relative_path


IGNORE_DIRS = {".venv", "__pycache__", ".git"}
SUPPORTED_EXTENSIONS = {"pdf", "docx", "md"}
TRACKED_UNSUPPORTED_EXTENSIONS = {"doc", "xls", "xlsx"}
OCR_MODES = ("auto", "force", "off")
MIN_PDF_TEXT_CHARS = 400
MIN_MEANINGFUL_PAGE_CHARS = 80
WINDOWS_OCR_TIMEOUT_SECONDS = 180


def normalize_whitespace(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")

    lines = [line.rstrip() for line in text.split("\n")]
    cleaned_lines: List[str] = []
    blank_count = 0

    for line in lines:
        if not line.strip():
            blank_count += 1
            if blank_count > 1:
                continue
        else:
            blank_count = 0
        cleaned_lines.append(line)

    joined_lines: List[str] = []
    buffer = ""
    for line in cleaned_lines:
        stripped = line.strip()
        if not stripped:
            if buffer:
                joined_lines.append(buffer)
                buffer = ""
            joined_lines.append("")
            continue

        if not buffer:
            buffer = stripped
            continue

        if re.search(r"[.?!:;]$", buffer):
            joined_lines.append(buffer)
            buffer = stripped
        else:
            buffer += " " + stripped

    if buffer:
        joined_lines.append(buffer)

    return "\n".join(joined_lines).strip()


def build_frontmatter(
    *,
    doc_id: str,
    title: str,
    source_file: str,
    category: str,
    source_type: str,
) -> str:
    created_at = dt.date.today().isoformat()
    return (
        "---\n"
        f'doc_id: "{doc_id}"\n'
        f'title: "{title}"\n'
        f'category: "{category}"\n'
        f'source_file: "{source_file}"\n'
        f'source_type: "{source_type}"\n'
        'language: "vi"\n'
        f'created_at: "{created_at}"\n'
        "---\n\n"
    )


def safe_title_from_name(path: Path) -> str:
    title = re.sub(r"[_\-]+", " ", path.stem)
    return re.sub(r"\s+", " ", title).strip()


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _relative_to_source_root(path: Path) -> Path:
    return path.relative_to(Path(RAW_DATA_DIR))


def _should_process_source(path: Path, route: str) -> bool:
    return route_matches_relative_path(_relative_to_source_root(path), route)


def _iter_source_files(route: str) -> Iterable[Path]:
    root = Path(RAW_DATA_DIR)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in IGNORE_DIRS and not name.startswith(".")]
        for filename in filenames:
            path = Path(dirpath) / filename
            if _should_process_source(path, route):
                yield path


def _ocr_script_path() -> Path:
    return Path(__file__).with_name("windows_pdf_ocr.ps1")


def _extract_pdf_pages_with_pypdf(src_path: Path) -> List[str]:
    reader = PdfReader(str(src_path))
    page_texts: List[str] = []
    for page in reader.pages:
        raw_text = page.extract_text() or ""
        page_texts.append(normalize_whitespace(raw_text))
    return page_texts


def _meaningful_page_count(page_texts: Sequence[str]) -> int:
    return sum(1 for text in page_texts if len(text.strip()) >= MIN_MEANINGFUL_PAGE_CHARS)


def _joined_length(page_texts: Sequence[str]) -> int:
    return len("\n".join(text for text in page_texts if text.strip()).strip())


def _should_ocr_pdf(page_texts: Sequence[str]) -> bool:
    total_chars = _joined_length(page_texts)
    meaningful_pages = _meaningful_page_count(page_texts)
    total_pages = max(len(page_texts), 1)

    if total_chars < MIN_PDF_TEXT_CHARS:
        return True
    if meaningful_pages == 0:
        return True
    if total_pages >= 3 and meaningful_pages <= max(1, total_pages // 4):
        return True
    return False


def _extract_pdf_pages_with_windows_ocr(src_path: Path) -> List[str]:
    if sys.platform != "win32":
        return []

    script_path = _ocr_script_path()
    if not script_path.exists():
        return []

    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-PdfPath",
        str(src_path),
    ]

    completed = subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        timeout=WINDOWS_OCR_TIMEOUT_SECONDS,
    )

    if completed.returncode != 0 or not completed.stdout.strip():
        return []

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []

    page_texts: List[str] = []
    for item in payload:
        page_texts.append(normalize_whitespace(str(item.get("text", ""))))
    return page_texts


def _choose_pdf_page_texts(src_path: Path, ocr_mode: str) -> Tuple[List[str], str]:
    pypdf_pages = _extract_pdf_pages_with_pypdf(src_path)
    if ocr_mode == "off":
        return pypdf_pages, "pypdf"

    if ocr_mode == "auto" and not _should_ocr_pdf(pypdf_pages):
        return pypdf_pages, "pypdf"

    ocr_pages = _extract_pdf_pages_with_windows_ocr(src_path)
    if not ocr_pages:
        return pypdf_pages, "pypdf"

    if ocr_mode == "force":
        return ocr_pages, "windows-ocr"

    if _joined_length(ocr_pages) > max(_joined_length(pypdf_pages) * 2, _joined_length(pypdf_pages) + 300):
        return ocr_pages, "windows-ocr"

    return pypdf_pages, "pypdf"


def _split_frontmatter(markdown: str) -> Tuple[str, str]:
    if markdown.startswith("---"):
        parts = markdown.split("---", 2)
        if len(parts) >= 3:
            frontmatter = "---" + parts[1] + "---\n\n"
            body = parts[2].lstrip()
            return frontmatter, body
    return "", markdown


def _frontmatter_has_key(frontmatter: str, key: str) -> bool:
    return bool(re.search(rf"^\s*{re.escape(key)}\s*:", frontmatter, flags=re.MULTILINE))


def _frontmatter_value(frontmatter: str, key: str) -> str:
    match = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.+?)\s*$", frontmatter, flags=re.MULTILINE)
    if not match:
        return ""

    return match.group(1).strip().strip('"').strip("'")


def _inject_frontmatter_key(frontmatter: str, key: str, value: str) -> str:
    if not frontmatter.startswith("---") or _frontmatter_has_key(frontmatter, key):
        return frontmatter

    parts = frontmatter.split("---", 2)
    if len(parts) < 3:
        return frontmatter

    meta = parts[1].strip("\n")
    meta = meta + f'\n{key}: "{value}"\n'
    return "---\n" + meta.strip("\n") + "\n---\n\n"


def normalize_markdown_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]

    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    cleaned_lines: List[str] = []
    blank_count = 0
    in_code_block = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            blank_count = 0
            cleaned_lines.append(line)
            continue

        if not stripped and not in_code_block:
            blank_count += 1
            if blank_count > 1:
                continue
        else:
            blank_count = 0

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def _build_pdf_markdown(page_texts: Sequence[str], title: str, frontmatter: str) -> str:
    parts: List[str] = [frontmatter, f"# {title}\n"]
    for page_number, text in enumerate(page_texts, start=1):
        if not text:
            continue
        parts.append(f"\n## Trang {page_number}\n")
        parts.append(text)
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def convert_pdf_to_md(src_path: Path, dst_path: Path, ocr_mode: str) -> str:
    rel_src = _relative_to_source_root(src_path)
    category = rel_src.parent.name
    title = safe_title_from_name(src_path)
    doc_id = str(rel_src).replace(os.sep, "_").rsplit(".", 1)[0]
    frontmatter = build_frontmatter(
        doc_id=doc_id,
        title=title,
        source_file=str(rel_src),
        category=category,
        source_type="pdf",
    )

    page_texts, extractor = _choose_pdf_page_texts(src_path, ocr_mode)
    content = _build_pdf_markdown(page_texts, title, frontmatter)

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_text(content, encoding="utf-8")
    print(f"[PDF:{extractor}] {rel_src} -> {dst_path.relative_to(Path(CLEAN_MD_DIR))}")
    return extractor


def convert_docx_to_md(src_path: Path, dst_path: Path) -> None:
    rel_src = _relative_to_source_root(src_path)
    category = rel_src.parent.name
    title = safe_title_from_name(src_path)
    doc_id = str(rel_src).replace(os.sep, "_").rsplit(".", 1)[0]

    document = Document(str(src_path))
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    normalized_text = normalize_whitespace("\n".join(paragraphs))

    parts: List[str] = [
        build_frontmatter(
            doc_id=doc_id,
            title=title,
            source_file=str(rel_src),
            category=category,
            source_type="docx",
        ),
        f"# {title}\n",
        normalized_text,
        "",
    ]

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_text("\n".join(parts).strip() + "\n", encoding="utf-8")
    print(f"[DOCX] {rel_src} -> {dst_path.relative_to(Path(CLEAN_MD_DIR))}")


def convert_markdown_to_clean_md(src_path: Path, dst_path: Path) -> None:
    rel_src = _relative_to_source_root(src_path)
    category = rel_src.parent.name
    raw_text = _read_text_file(src_path)
    frontmatter, body = _split_frontmatter(raw_text)

    title = _frontmatter_value(frontmatter, "title") or safe_title_from_name(src_path)
    doc_id = str(rel_src).replace(os.sep, "_").rsplit(".", 1)[0]

    if frontmatter:
        for key, value in (
            ("doc_id", doc_id),
            ("title", title),
            ("category", category),
            ("source_file", str(rel_src)),
            ("source_type", "md"),
            ("language", "vi"),
            ("created_at", dt.date.today().isoformat()),
        ):
            frontmatter = _inject_frontmatter_key(frontmatter, key, value)
    else:
        frontmatter = build_frontmatter(
            doc_id=doc_id,
            title=title,
            source_file=str(rel_src),
            category=category,
            source_type="md",
        )

    normalized_body = normalize_markdown_text(body)
    if not re.search(r"^\s*#{1,6}\s+\S", normalized_body, flags=re.MULTILINE):
        normalized_body = f"# {title}\n\n{normalized_body}".strip()

    content = f"{frontmatter}{normalized_body.strip()}\n"
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_text(content, encoding="utf-8")
    print(f"[MD] {rel_src} -> {dst_path.relative_to(Path(CLEAN_MD_DIR))}")


def _build_report_path(route: str) -> Path:
    return Path(CLEAN_MD_DIR) / "_reports" / f"{route}_source_report.json"


def _prune_empty_dirs(root: Path) -> None:
    for directory in sorted(root.rglob("*"), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()


def _clear_matching_output(route: str) -> None:
    out_root = Path(CLEAN_MD_DIR)
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


def build_clean_markdown(route: str = "all", ocr_mode: str = "auto") -> Dict[str, object]:
    route = route.strip().lower()
    ocr_mode = ocr_mode.strip().lower()

    if route not in SOURCE_ROUTES:
        raise ValueError(f"Unsupported route: {route}")
    if ocr_mode not in OCR_MODES:
        raise ValueError(f"Unsupported OCR mode: {ocr_mode}")

    root = Path(RAW_DATA_DIR)
    out_root = Path(CLEAN_MD_DIR)
    if not root.exists():
        raise FileNotFoundError(f"RAW_DATA_DIR does not exist: {root}")

    _clear_matching_output(route)

    stats: Dict[str, object] = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source_root": str(root),
        "output_root": str(out_root),
        "route": route,
        "ocr_mode": ocr_mode,
        "converted": 0,
        "pdf_files": 0,
        "docx_files": 0,
        "md_files": 0,
        "ocr_used": 0,
        "unsupported_files": [],
    }

    unsupported_paths: List[str] = []
    for src_path in sorted(_iter_source_files(route)):
        ext = src_path.suffix.lower().lstrip(".")
        rel = _relative_to_source_root(src_path)

        if ext in TRACKED_UNSUPPORTED_EXTENSIONS:
            unsupported_paths.append(str(rel))
            continue

        if ext not in SUPPORTED_EXTENSIONS:
            continue

        dst_path = out_root / rel.with_suffix(".md")

        if ext == "pdf":
            stats["pdf_files"] = int(stats["pdf_files"]) + 1
            extractor = convert_pdf_to_md(src_path, dst_path, ocr_mode)
            if extractor == "windows-ocr":
                stats["ocr_used"] = int(stats["ocr_used"]) + 1
        elif ext == "docx":
            stats["docx_files"] = int(stats["docx_files"]) + 1
            convert_docx_to_md(src_path, dst_path)
        else:
            stats["md_files"] = int(stats["md_files"]) + 1
            convert_markdown_to_clean_md(src_path, dst_path)

        stats["converted"] = int(stats["converted"]) + 1

    stats["unsupported_files"] = unsupported_paths
    report_path = _build_report_path(route)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert source files in datadoan into clean markdown.")
    parser.add_argument(
        "--route",
        choices=SOURCE_ROUTES,
        default="all",
        help="Rebuild only handbook, only policy, or all source markdown.",
    )
    parser.add_argument(
        "--ocr",
        choices=OCR_MODES,
        default="auto",
        help="Control PDF OCR fallback on Windows.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        stats = build_clean_markdown(route=args.route, ocr_mode=args.ocr)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    print("")
    print("Done rebuilding clean markdown.")
    print(f"Route: {stats['route']}")
    print(f"Converted: {stats['converted']}")
    print(
        f"PDF: {stats['pdf_files']} | DOCX: {stats['docx_files']} | MD: {stats['md_files']} | OCR used: {stats['ocr_used']}"
    )
    print(f"Unsupported tracked files: {len(stats['unsupported_files'])}")
    print(f"Report: {_build_report_path(args.route)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
