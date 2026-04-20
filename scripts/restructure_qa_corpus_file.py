from __future__ import annotations

import argparse
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


FRONTMATTER_SPLIT = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
PAGE_BLOCK_RE = re.compile(r"^## Page (\d+)\s*$", re.MULTILINE)
QA_PAIR_RE = re.compile(
    r"\*\*Q:\*\*\s*(.+?)\n\*\*A:\*\*\s*(.*?)(?=\n\*\*Q:\*\*|\n##\s+|\Z)",
    re.DOTALL,
)


@dataclass
class Chunk:
    chunk_id: str
    title: str
    section_path: str
    pages: str
    text: str


@dataclass
class QuestionEntry:
    question_id: str
    question: str
    answer: str
    mapped_chunk_id: str
    mapped_chunk_title: str
    mapped_pages: str
    mapped_excerpt: str
    mapping_basis: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Restructure one qa_generated_fixed markdown file into RAG-friendly context plus a separate question mapping file.",
    )
    parser.add_argument("--qa-file", type=Path, required=True, help="Path to the qa_generated_fixed markdown file.")
    parser.add_argument(
        "--clean-file",
        type=Path,
        default=None,
        help="Optional path to the matching clean_data markdown file. If omitted, the script resolves it from frontmatter.",
    )
    parser.add_argument(
        "--questions-file",
        type=Path,
        default=None,
        help="Optional output path for the extracted question file. Default: sibling file with .questions.md suffix.",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=2200,
        help="Soft per-chunk size limit before splitting long sections.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without writing files.",
    )
    return parser.parse_args()


def split_frontmatter(text: str) -> tuple[dict, str]:
    match = FRONTMATTER_SPLIT.match(text)
    if not match:
        return {}, text
    raw_frontmatter = match.group(1)
    body = text[match.end() :]
    metadata: dict[str, object] = {}
    for line in raw_frontmatter.splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        metadata[key.strip()] = parse_frontmatter_value(raw_value.strip())
    return metadata, body


def parse_frontmatter_value(raw_value: str) -> object:
    if not raw_value:
        return ""
    if raw_value.startswith(("\"", "[", "{")) or raw_value in {"true", "false", "null"}:
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError:
            pass
    if raw_value.startswith("'") and raw_value.endswith("'"):
        return raw_value[1:-1]
    if raw_value.startswith('"') and raw_value.endswith('"'):
        return raw_value[1:-1]
    return raw_value


def slugify(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "_", ascii_value.lower()).strip("_") or "document"


def ascii_fold(value: str) -> str:
    return (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )


def find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "clean_data").exists() and (candidate / "data").exists():
            return candidate
    raise FileNotFoundError(f"Khong suy ra duoc repo root tu: {start}")


def parse_qa_pairs(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for question, answer in QA_PAIR_RE.findall(text):
        pairs.append((clean_inline_text(question), clean_answer_text(answer)))
    return pairs


def clean_inline_text(text: str) -> str:
    text = text.replace("**", "").replace("`", "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def clean_answer_text(text: str) -> str:
    lines = []
    for raw_line in text.strip().splitlines():
        line = clean_inline_text(raw_line)
        if not line:
            continue
        if line.startswith("-"):
            line = f"- {line.lstrip('-').strip()}"
        lines.append(line)
    return "\n".join(lines)


def resolve_clean_file(
    qa_file: Path,
    qa_meta: dict,
    explicit_clean_file: Optional[Path],
    repo_root: Path,
) -> Path:
    if explicit_clean_file is not None:
        return explicit_clean_file

    source_relative = str(qa_meta.get("source", "")).strip()
    if not source_relative:
        source_relative = str(qa_meta.get("source_clean_file", "")).strip()
    if not source_relative:
        raise FileNotFoundError("Khong tim thay frontmatter `source` de suy ra file clean_data.")

    if source_relative.startswith("clean_data/") or source_relative.startswith("clean_data\\"):
        clean_file = repo_root / Path(source_relative)
    else:
        clean_file = repo_root / "clean_data" / Path(source_relative)
    if not clean_file.exists():
        raise FileNotFoundError(f"Khong tim thay clean_data tuong ung: {clean_file}")
    return clean_file


def parse_pages(clean_body: str) -> list[tuple[int, str]]:
    matches = list(PAGE_BLOCK_RE.finditer(clean_body))
    pages: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        page_number = int(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(clean_body)
        pages.append((page_number, clean_body[start:end].strip()))
    return pages


def page_lines(page_text: str, *, for_toc: bool = False) -> list[str]:
    lines: list[str] = []
    for raw_line in page_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("<!--"):
            continue
        line = line.replace("**", "")
        line = line.replace("", "- ")
        line = re.sub(r"\s+", " ", line).strip()
        folded = ascii_fold(line)
        if re.match(r"^\d+\s+(?=(phan|chuong|[ivxlc]+\.)\b)", folded):
            line = re.sub(r"^\d+\s+", "", line)
        if re.fullmatch(r"\d+", line):
            continue
        if ascii_fold(line) in {"noi dung trang", "muc luc", "chon muc nay"}:
            continue
        if for_toc:
            line = re.sub(r"\s+\d{1,3}$", "", line).strip()
        lines.append(line)
    return lines


def is_toc_page(page_number: int, page_text: str) -> bool:
    if page_number > 10:
        return False
    preview = ascii_fold(" ".join(page_text.splitlines()[:12]))
    return "muc luc" in preview or "noi dung trang" in preview


def normalize_heading(line: str) -> str:
    title = re.sub(r"^\d+\s+", "", line).strip()
    title = re.sub(r"\s+\d{1,3}$", "", title).strip()
    title = re.sub(r"\s+", " ", title)
    return title


def looks_tabular(line: str) -> bool:
    digit_count = sum(char.isdigit() for char in line)
    word_count = len(line.split())
    uppercase_count = sum(char.isupper() for char in line)
    return digit_count >= 6 and word_count >= 8 and uppercase_count < max(8, word_count)


def detect_heading(line: str) -> Optional[tuple[str, str]]:
    candidate = normalize_heading(line)
    if not candidate:
        return None
    folded = ascii_fold(candidate)

    if re.match(r"^phan\s+[ivxlc]+\b", folded):
        return "part", candidate

    if re.match(r"^chuong\s+[ivxlc]+\b", folded):
        return "chapter", candidate

    if re.match(r"^[ivxlc]+\.\s+", folded) and not looks_tabular(candidate):
        return "section", candidate

    if re.match(r"^\d+(?:\.\d+){0,2}\.?\s+[^\d]", candidate) and not looks_tabular(candidate):
        return "numeric", candidate

    letters = sum(char.isalpha() for char in candidate)
    uppercase_letters = sum(char.isupper() for char in candidate if char.isalpha())
    word_count = len(candidate.split())
    if (
        letters >= 6
        and uppercase_letters >= max(6, int(letters * 0.7))
        and word_count <= 12
        and not looks_tabular(candidate)
    ):
        return "upper", candidate

    return None


def format_chunk_body(lines: list[str]) -> str:
    paragraphs: list[str] = []
    buffer: list[str] = []
    previous_line = ""
    for line in lines:
        if not line:
            if buffer:
                paragraphs.append(" ".join(buffer).strip())
                buffer.clear()
            previous_line = ""
            continue

        if line.startswith("- "):
            if buffer:
                paragraphs.append(" ".join(buffer).strip())
                buffer.clear()
            paragraphs.append(line)
            previous_line = line
            continue

        if looks_tabular(line) or line.endswith(":"):
            if buffer:
                paragraphs.append(" ".join(buffer).strip())
                buffer.clear()
            paragraphs.append(line)
            previous_line = line
            continue

        if previous_line.endswith((".", ":", ";", "?", "!")) and buffer:
            paragraphs.append(" ".join(buffer).strip())
            buffer = [line]
        else:
            buffer.append(line)
        previous_line = line

    if buffer:
        paragraphs.append(" ".join(buffer).strip())

    cleaned = [paragraph for paragraph in paragraphs if paragraph]
    return "\n\n".join(cleaned)


def chunk_text_length(lines: list[str]) -> int:
    return sum(len(line) for line in lines) + max(0, len(lines) - 1)


def current_section_path(levels: dict[int, Optional[str]]) -> list[str]:
    return [level for _, level in sorted(levels.items()) if level]


def most_specific_title(levels: dict[int, Optional[str]], fallback: str) -> str:
    path = current_section_path(levels)
    return path[-1] if path else fallback


def excerpt(text: str, limit: int = 220) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def safe_console_text(value: object) -> str:
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def render_context_markdown(
    *,
    output_title: str,
    repo_root: Path,
    qa_file: Path,
    clean_file: Path,
    clean_meta: dict,
    question_file: Path,
    chunks: list[Chunk],
    generated_at: str,
) -> str:
    question_relative = question_file.relative_to(repo_root).as_posix()
    clean_relative = clean_file.relative_to(repo_root).as_posix()
    qa_relative = qa_file.relative_to(repo_root).as_posix()

    frontmatter_lines = [
        "---",
        f'title: "{output_title}"',
        f'source_qa_file: "{qa_relative}"',
        f'source_clean_file: "{clean_relative}"',
        f'source_pdf: "{clean_meta.get("source_relative_path", "")}"',
        f'questions_file: "{question_relative}"',
        f'generated_at: "{generated_at}"',
        'generator: "restructure_qa_corpus_file.py"',
        f'document_group: "{clean_meta.get("inferred_group", "")}"',
        f'document_topic: "{clean_meta.get("inferred_topic", "")}"',
        f'document_type: "{clean_meta.get("inferred_document_type", "")}"',
        f'school_years: {json.dumps(clean_meta.get("inferred_school_years", []), ensure_ascii=False)}',
        f"chunk_count: {len(chunks)}",
        "---",
        "",
        f"# {output_title}",
        "",
        "Tai lieu nay da duoc lam sach khoi phan cau hoi va tai cau truc thanh cac chunk logic de toi uu retrieval.",
        "",
    ]

    parts = ["\n".join(frontmatter_lines)]
    for chunk in chunks:
        parts.append(
            "\n".join(
                [
                    f"## {chunk.title}",
                    "",
                    f"- `chunk_id`: `{chunk.chunk_id}`",
                    f"- `section_path`: `{chunk.section_path}`",
                    f"- `pages`: `{chunk.pages}`",
                    "",
                    chunk.text,
                    "",
                ]
            )
        )
    return "\n".join(parts).rstrip() + "\n"


def render_questions_markdown(
    *,
    output_title: str,
    repo_root: Path,
    context_file: Path,
    questions: list[QuestionEntry],
    generated_at: str,
) -> str:
    context_relative = context_file.relative_to(repo_root).as_posix()
    frontmatter_lines = [
        "---",
        f'title: "{output_title}"',
        f'source_context_file: "{context_relative}"',
        f'generated_at: "{generated_at}"',
        'generator: "restructure_qa_corpus_file.py"',
        f"question_count: {len(questions)}",
        "---",
        "",
        f"# {output_title}",
        "",
        "Danh sach nay chi giu cau hoi va mapping sang cac chunk context tuong ung trong file RAG.",
        "",
    ]

    parts = ["\n".join(frontmatter_lines)]
    for index, question in enumerate(questions, start=1):
        parts.append(
            "\n".join(
                [
                    f"## Question {index:02d}",
                    "",
                    f"- `question_id`: `{question.question_id}`",
                    f"- `mapped_chunk_id`: `{question.mapped_chunk_id}`",
                    f"- `mapped_chunk_title`: `{question.mapped_chunk_title}`",
                    f"- `mapped_pages`: `{question.mapped_pages}`",
                    f"- `mapping_basis`: {question.mapping_basis}",
                    "",
                    f"**Question:** {question.question}",
                    "",
                    "**Legacy answer snapshot:**",
                    question.answer,
                    "",
                    f"**Answer anchor excerpt:** {question.mapped_excerpt}",
                    "",
                ]
            )
        )
    return "\n".join(parts).rstrip() + "\n"


def build_chunks(clean_meta: dict, pages: list[tuple[int, str]], max_chars: int) -> list[Chunk]:
    document_title = str(clean_meta.get("title") or "Tai lieu")
    prefix = slugify(document_title)
    chunks: list[Chunk] = []

    overview_chunk = Chunk(
        chunk_id=f"{prefix}__0000",
        title="Chunk 000 - Ho so tai lieu va luu y khai thac",
        section_path="Ho so tai lieu",
        pages="metadata",
        text="\n".join(
            [
                f"Tai lieu thuoc nhom tri thuc: {clean_meta.get('inferred_group', '')}.",
                f"Chu de tai lieu: {clean_meta.get('inferred_topic', '')}.",
                f"Loai tai lieu: {clean_meta.get('inferred_document_type', '')}.",
                f"Nam hoc ap dung: {', '.join(clean_meta.get('inferred_school_years', [])) or 'khong ro'}.",
                f"Nguon PDF tuong ung: {clean_meta.get('source_relative_path', '')}.",
                (
                    "Trang thai du lieu: "
                    f"{clean_meta.get('document_status', '')}; body_source={clean_meta.get('body_source', '')}; "
                    f"ocr_required={clean_meta.get('ocr_required', '')}; usable_text_ratio={clean_meta.get('usable_text_ratio', '')}."
                ),
                "Goi y khai thac RAG: uu tien retrieval theo section_path va OCR lai cac trang yeu neu can tang do sach cua context.",
            ]
        ),
    )
    chunks.append(overview_chunk)

    toc_pages: list[tuple[int, str]] = []
    body_pages: list[tuple[int, str]] = []
    for page_number, page_text in pages:
        if not body_pages and is_toc_page(page_number, page_text):
            toc_pages.append((page_number, page_text))
        else:
            body_pages.append((page_number, page_text))

    if toc_pages:
        toc_lines: list[str] = []
        seen_toc_lines: set[str] = set()
        for _, page_text in toc_pages:
            for line in page_lines(page_text, for_toc=True):
                if not line or line in seen_toc_lines:
                    continue
                seen_toc_lines.add(line)
                toc_lines.append(f"- {line}" if not line.startswith("- ") else line)
        if toc_lines:
            toc_page_range = (
                str(toc_pages[0][0])
                if toc_pages[0][0] == toc_pages[-1][0]
                else f"{toc_pages[0][0]}-{toc_pages[-1][0]}"
            )
            chunks.append(
                Chunk(
                    chunk_id=f"{prefix}__0001",
                    title="Chunk 001 - Muc luc va pham vi tri thuc",
                    section_path="Muc luc > Pham vi noi dung",
                    pages=toc_page_range,
                    text="\n".join(
                        [
                            f"Tai lieu nguon: {document_title}.",
                            "Chunk nay tom tat muc luc de ho tro dinh tuyen retrieval theo dung phan kien thuc.",
                            "",
                            *toc_lines,
                        ]
                    ).strip(),
                )
            )

    levels: dict[int, Optional[str]] = {1: None, 2: None, 3: None, 4: None}
    current_lines: list[str] = []
    current_start_page: Optional[int] = None
    current_end_page: Optional[int] = None
    current_snapshot: dict[int, Optional[str]] = levels.copy()
    section_counts: dict[tuple[str, ...], int] = {}

    def flush_current_chunk() -> None:
        nonlocal current_lines, current_start_page, current_end_page, current_snapshot
        if not current_lines or current_start_page is None or current_end_page is None:
            current_lines = []
            current_start_page = None
            current_end_page = None
            current_snapshot = levels.copy()
            return

        section_path_list = current_section_path(current_snapshot)
        section_key = tuple(section_path_list) if section_path_list else ("Tong quan",)
        section_counts[section_key] = section_counts.get(section_key, 0) + 1
        occurrence = section_counts[section_key]
        specific_title = most_specific_title(current_snapshot, document_title)
        display_title = specific_title if occurrence == 1 else f"{specific_title} (phan {occurrence})"
        pages_value = (
            str(current_start_page)
            if current_start_page == current_end_page
            else f"{current_start_page}-{current_end_page}"
        )
        chunk_number = len(chunks)
        chunk_id = f"{prefix}__{chunk_number:04d}"
        section_path_value = " > ".join(section_path_list) if section_path_list else document_title
        body_text = format_chunk_body(current_lines)
        chunk_text = "\n".join(
            [
                f"Tai lieu nguon: {document_title}.",
                f"Ngu canh chunk: {section_path_value}.",
                "",
                body_text,
            ]
        ).strip()
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                title=f"Chunk {chunk_number:03d} - {display_title}",
                section_path=section_path_value,
                pages=pages_value,
                text=chunk_text,
            )
        )
        current_lines = []
        current_start_page = None
        current_end_page = None
        current_snapshot = levels.copy()

    for page_number, page_text in body_pages:
        cleaned_lines = page_lines(page_text)
        if not cleaned_lines:
            continue

        for line in cleaned_lines:
            heading = detect_heading(line)
            if heading is not None:
                kind, title = heading
                if kind == "part":
                    flush_current_chunk()
                    levels[1] = title
                    levels[2] = None
                    levels[3] = None
                    levels[4] = None
                    current_snapshot = levels.copy()
                    continue
                if kind == "chapter":
                    flush_current_chunk()
                    levels[2] = title
                    levels[3] = None
                    levels[4] = None
                    current_snapshot = levels.copy()
                    continue
                if kind in {"section", "upper"}:
                    if current_lines and chunk_text_length(current_lines) >= 700:
                        flush_current_chunk()
                    levels[3] = title
                    levels[4] = None
                    current_snapshot = levels.copy()
                    if current_start_page is None:
                        current_start_page = page_number
                    current_end_page = page_number
                    current_lines.append(title)
                    continue
                if kind == "numeric":
                    if current_lines and chunk_text_length(current_lines) >= 1200:
                        flush_current_chunk()
                    levels[4] = title
                    current_snapshot = levels.copy()
                    if current_start_page is None:
                        current_start_page = page_number
                    current_end_page = page_number
                    current_lines.append(title)
                    continue

            if current_start_page is None:
                current_start_page = page_number
                current_snapshot = levels.copy()
            current_end_page = page_number
            if current_lines and current_lines[-1] == line:
                continue
            current_lines.append(line)

            if chunk_text_length(current_lines) >= max_chars and line.endswith((".", ";", ":", "?", "!")):
                flush_current_chunk()

    flush_current_chunk()
    return chunks


def build_question_entries(
    qa_pairs: list[tuple[str, str]],
    chunks: list[Chunk],
) -> list[QuestionEntry]:
    if not chunks:
        return []

    overview_chunk = chunks[0]
    toc_chunk = chunks[1] if len(chunks) > 1 else chunks[0]

    entries: list[QuestionEntry] = []
    for index, (question, answer) in enumerate(qa_pairs, start=1):
        lowered = f"{question} {answer}".lower()
        target_chunk = toc_chunk if any(keyword in lowered for keyword in ["tóm tắt", "nội dung"]) else overview_chunk
        mapping_basis = (
            "Cau hoi hoi ve pham vi noi dung/muc luc nen map vao chunk muc luc."
            if target_chunk.chunk_id == toc_chunk.chunk_id
            else "Cau hoi hoi ve ho so tai lieu, metadata hoac tinh trang ingest nen map vao chunk ho so tai lieu."
        )
        entries.append(
            QuestionEntry(
                question_id=f"q{index:03d}",
                question=question,
                answer=answer,
                mapped_chunk_id=target_chunk.chunk_id,
                mapped_chunk_title=target_chunk.title,
                mapped_pages=target_chunk.pages,
                mapped_excerpt=excerpt(target_chunk.text),
                mapping_basis=mapping_basis,
            )
        )
    return entries


def main() -> int:
    args = parse_args()
    qa_file = args.qa_file.resolve()
    if not qa_file.exists():
        raise FileNotFoundError(f"Khong tim thay qa file: {qa_file}")
    repo_root = find_repo_root(qa_file)
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")

    qa_text = qa_file.read_text(encoding="utf-8", errors="ignore")
    qa_meta, qa_body = split_frontmatter(qa_text)
    qa_pairs = parse_qa_pairs(qa_body)

    clean_file = resolve_clean_file(
        qa_file,
        qa_meta,
        args.clean_file.resolve() if args.clean_file else None,
        repo_root,
    )
    clean_text = clean_file.read_text(encoding="utf-8", errors="ignore")
    clean_meta, clean_body = split_frontmatter(clean_text)
    pages = parse_pages(clean_body)

    output_questions_file = (
        args.questions_file.resolve()
        if args.questions_file
        else qa_file.with_suffix(".questions.md")
    )

    chunks = build_chunks(clean_meta, pages, args.max_chars)
    question_entries = build_question_entries(qa_pairs, chunks)

    context_title = f"RAG Context - {clean_meta.get('title', qa_file.stem)}"
    questions_title = f"Question Set - {clean_meta.get('title', qa_file.stem)}"

    context_markdown = render_context_markdown(
        output_title=context_title,
        repo_root=repo_root,
        qa_file=qa_file,
        clean_file=clean_file,
        clean_meta=clean_meta,
        question_file=output_questions_file,
        chunks=chunks,
        generated_at=generated_at,
    )
    questions_markdown = render_questions_markdown(
        output_title=questions_title,
        repo_root=repo_root,
        context_file=qa_file,
        questions=question_entries,
        generated_at=generated_at,
    )

    if args.dry_run:
        print(f"Context file: {safe_console_text(qa_file)}")
        print(f"Questions file: {safe_console_text(output_questions_file)}")
        print(f"Questions extracted: {len(question_entries)}")
        print(f"Chunks generated: {len(chunks)}")
        return 0

    qa_file.write_text(context_markdown, encoding="utf-8")
    output_questions_file.write_text(questions_markdown, encoding="utf-8")
    print(f"Rewrote context file: {safe_console_text(qa_file)}")
    print(f"Wrote question file: {safe_console_text(output_questions_file)}")
    print(f"Questions extracted: {len(question_entries)}")
    print(f"Chunks generated: {len(chunks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
