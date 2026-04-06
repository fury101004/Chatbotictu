#!/usr/bin/env python
# Usage:
#   python generate_qa_from_markdown.py --input clean_data --output data/qa_generated --force
#   python generate_qa_from_markdown.py --input clean_data --output data/qa_generated --provider heuristic --mode file
#   python generate_qa_from_markdown.py --input "clean_data/Bao Hiem Y Te" --output data/qa_generated --mode topdir

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


SCRIPT_NAME = "generate_qa_from_markdown.py"


@dataclass
class ContextDoc:
    source_path: Path
    relative_path: Path
    title: str
    metadata: dict[str, object]
    body: str


def safe_print(message: str = "", *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    encoding = stream.encoding or "utf-8"
    try:
        print(message, file=stream)
    except UnicodeEncodeError:
        fallback = message.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(fallback, file=stream)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate QA markdown files from clean_data contexts.")
    parser.add_argument("--input", default="clean_data", help="Input markdown file or directory.")
    parser.add_argument("--output", default="data/qa_generated", help="Output directory for generated QA files.")
    parser.add_argument("--mode", choices=("file", "topdir"), default="file", help="Generate one QA file per file or per top-level folder.")
    parser.add_argument("--provider", choices=("auto", "gemini", "heuristic"), default="auto", help="Generation provider.")
    parser.add_argument("--questions-per-item", type=int, default=6, help="Target QA count per generated file.")
    parser.add_argument("--include-pending", action="store_true", help="Include files under _ocr_pending.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing QA files.")
    parser.add_argument("--verbose", action="store_true", help="Print detailed progress logs.")
    parser.add_argument("--model", default="gemini-2.5-flash-lite", help="Gemini model name when provider=gemini/auto.")
    parser.add_argument("--max-context-chars", type=int, default=16000, help="Maximum source characters sent to the generator.")
    return parser.parse_args()


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
    return ascii_text.strip("-") or "untitled"


def split_front_matter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---\n"):
        return {}, text

    end_marker = text.find("\n---\n", 4)
    if end_marker == -1:
        return {}, text

    raw_meta = text[4:end_marker]
    body = text[end_marker + 5 :].lstrip()
    metadata: dict[str, object] = {}
    for line in raw_meta.splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if not key:
            continue
        try:
            metadata[key] = json.loads(raw_value)
        except Exception:
            metadata[key] = raw_value.strip('"')
    return metadata, body


def normalize_body(body: str) -> str:
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    body = re.sub(r"<!--.*?-->", "", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def read_context_doc(source_path: Path, input_root: Path) -> ContextDoc:
    text = source_path.read_text(encoding="utf-8", errors="ignore")
    metadata, body = split_front_matter(text)
    body = normalize_body(body)
    title = str(metadata.get("title") or source_path.stem).strip()
    return ContextDoc(
        source_path=source_path,
        relative_path=source_path.relative_to(input_root),
        title=title,
        metadata=metadata,
        body=body,
    )


def collect_input_docs(input_path: Path, include_pending: bool) -> tuple[Path, list[ContextDoc]]:
    if input_path.is_file():
        root = input_path.parent
        return root, [read_context_doc(input_path, root)]

    root = input_path
    docs: list[ContextDoc] = []
    for path in sorted(root.rglob("*.md"), key=lambda item: str(item).lower()):
        if not include_pending and "_ocr_pending" in path.parts:
            continue
        docs.append(read_context_doc(path, root))
    return root, docs


def group_docs(docs: list[ContextDoc], mode: str) -> list[tuple[str, list[ContextDoc]]]:
    if mode == "file":
        return [(str(doc.relative_path.with_suffix("")), [doc]) for doc in docs]

    grouped: dict[str, list[ContextDoc]] = {}
    for doc in docs:
        top_dir = doc.relative_path.parts[0] if len(doc.relative_path.parts) > 1 else doc.relative_path.stem
        grouped.setdefault(top_dir, []).append(doc)
    return sorted(grouped.items(), key=lambda item: item[0].lower())


def first_meaningful_paragraphs(body: str, limit: int = 2) -> list[str]:
    paragraphs = []
    for piece in re.split(r"\n\s*\n", body):
        cleaned = piece.strip()
        if not cleaned:
            continue
        if cleaned.startswith("#"):
            continue
        if cleaned.startswith("> "):
            continue
        if cleaned.startswith("## Extraction Status"):
            continue
        if cleaned.startswith("## Missing Pages"):
            continue
        if cleaned.startswith("## Search Keywords"):
            continue
        if cleaned.startswith("## Suggested Questions"):
            continue
        if cleaned.startswith("## Document Profile"):
            continue
        if cleaned.startswith("## Inferred Summary"):
            continue
        if len(cleaned) < 40:
            continue
        paragraphs.append(cleaned)
        if len(paragraphs) >= limit:
            break
    return paragraphs


def guess_document_type(title: str) -> str:
    title_slug = slugify(title).replace("-", " ")
    mapping = [
        ("thông báo", "Thông báo"),
        ("tb ", "Thông báo"),
        ("tb-", "Thông báo"),
        ("quyết định", "Quyết định"),
        ("thong tu", "Thong tu"),
        ("nghi dinh", "Nghi dinh"),
        ("ke hoach", "Kế hoạch"),
        ("cong van", "Công văn"),
        ("cv ", "Công văn"),
        ("qd ", "Quyết định"),
        ("so tay", "So tay"),
        ("quy dinh", "Quy dinh"),
        ("quy che", "Quy che"),
    ]
    for key, label in mapping:
        if key in title_slug:
            return label
    return "Van ban"


def build_heuristic_qas(doc: ContextDoc, question_limit: int) -> list[tuple[str, list[str]]]:
    metadata = doc.metadata
    document_type = str(metadata.get("inferred_document_type") or guess_document_type(doc.title)).strip()
    group_name = str(metadata.get("inferred_group") or metadata.get("source_relative_path") or doc.relative_path.parent.name).strip()
    topic_name = str(metadata.get("inferred_topic") or doc.title).strip()
    years = metadata.get("inferred_years") or []
    school_years = metadata.get("inferred_school_years") or []
    document_status = str(metadata.get("document_status") or "unknown").strip()
    ocr_required = bool(metadata.get("ocr_required"))
    body_source = str(metadata.get("body_source") or "unknown").strip()
    usable_ratio = metadata.get("usable_text_ratio")
    paragraphs = first_meaningful_paragraphs(doc.body, limit=2)

    qas: list[tuple[str, list[str]]] = [
        (
            "Tài liệu này thuộc nhóm nào?",
            [
                f"Tài liệu được xếp vào nhóm {group_name}.",
                f"Chu de chinh dang duoc gan la {topic_name}.",
            ],
        ),
        (
            "Đây là loại văn bản gì?",
            [
                f"Tài liệu này được nhận dạng gần đúng là {document_type}.",
                f"Ten file hien tai la {doc.title}.",
            ],
        ),
    ]

    if years or school_years:
        answer_lines = []
        if years:
            answer_lines.append(f"Cac nam duoc nhan thay trong context: {', '.join(str(year) for year in years)}.")
        if school_years:
            answer_lines.append(f"Cac nam hoc duoc nhan thay: {', '.join(str(item) for item in school_years)}.")
        qas.append(("Tài liệu này áp dụng cho năm nào hoặc giai đoạn nào?", answer_lines))

    if paragraphs:
        qas.append(
            (
                "Nội dung tóm tắt hiện tại cho thấy điều gì?",
                [paragraphs[0]] + ([paragraphs[1]] if len(paragraphs) > 1 else []),
            )
        )

    qas.append(
        (
            "Tình trạng dữ liệu của tài liệu này hiện tại ra sao?",
            [
                f"Document status hien tai la {document_status}.",
                f"Body source dang la {body_source}.",
                f"OCR required = {'true' if ocr_required else 'false'}.",
            ]
            + ([f"Ti le trang co text su dung duoc la {usable_ratio}."] if usable_ratio is not None else []),
        )
    )

    qas.append(
        (
            "Can lam gi neu muon chatbot tra loi tot hon tu tai lieu nay?",
            [
                "Can bo sung body text ro rang, sach va day du hon cho context.",
                "Neu tai lieu la scan hoac body con thieu, nen OCR va chay lai quy trinh tao QA.",
            ],
        )
    )

    qas.append(
        (
            "Khi hoi chatbot ve tai lieu nay, nen hoi theo cach nao?",
            [
                "Nen hoi ro chu de, loai van ban, nam hoc hoac nam ap dung.",
                "Neu tai lieu thuoc nhom hoc bong, ren luyen, tot nghiep, BHYT... thi nen neu dung nhom do trong cau hoi.",
            ],
        )
    )

    return qas[: max(question_limit, 1)]


def build_group_heuristic_qas(group_name: str, docs: list[ContextDoc], question_limit: int) -> list[tuple[str, list[str]]]:
    titles = [doc.title for doc in docs[:5]]
    years: list[str] = []
    for doc in docs:
        for item in doc.metadata.get("inferred_years", []) if isinstance(doc.metadata.get("inferred_years"), list) else []:
            if str(item) not in years:
                years.append(str(item))

    pending_count = sum(1 for doc in docs if str(doc.metadata.get("document_status")) != "clean")
    clean_count = len(docs) - pending_count
    qas = [
        (
            f"Nhom tai lieu {group_name} lien quan den van de gi?",
            [
                f"Nhom nay hien co {len(docs)} context markdown duoc gom lai.",
                f"Cac tai lieu mau gom: {', '.join(titles)}." if titles else "Nhom nay chua co tai lieu mau de liet ke.",
            ],
        ),
        (
            "Muc dich su dung cua nhom context nay la gi?",
            [
                "Nhom context nay phu hop de tao bo cau hoi tra loi, bo FAQ, hoac lam nguon tra cuu cho chatbot.",
                "Noi dung QA nen tap trung vao chu de, doi tuong ap dung, moc thoi gian va cach hoi them khi thieu thong tin.",
            ],
        ),
        (
            "Tinh trang sach cua nhom tai lieu nay hien tai the nao?",
            [
                f"So tai lieu co body tuong doi sach: {clean_count}.",
                f"So tai lieu van dang pending OCR hoac body chua day du: {pending_count}.",
            ],
        ),
    ]

    if years:
        qas.append(
            (
                "Nhom nay lien quan den cac nam nao?",
                [f"Cac nam duoc nhan thay trong metadata: {', '.join(years[:12])}."]
            )
        )

    qas.append(
        (
            "Nen dat cau hoi cho chatbot theo cach nao?",
            [
                f"Nen neu ro nhom '{group_name}' trong cau hoi neu muon chatbot tim dung context.",
                "Neu co nam hoc, so van ban, dot xet, hoc ky hoac doi tuong ap dung thi nen noi ro trong cau hoi.",
            ],
        )
    )

    qas.append(
        (
            "Can lam gi de nang chat luong QA cho nhom nay?",
            [
                "Tien OCR cac file dang pending va bo sung body text day du.",
                "Sau do sinh lai QA tu body da lam sach de co cau tra loi sat noi dung goc hon.",
            ],
        )
    )

    return qas[: max(question_limit, 1)]


def format_qa_markdown(title: str, source_label: str, provider: str, qas: list[tuple[str, list[str]]]) -> str:
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        "---",
        f'title: {json.dumps(title, ensure_ascii=False)}',
        f'source: {json.dumps(source_label, ensure_ascii=False)}',
        f'generated_at: {json.dumps(generated_at, ensure_ascii=False)}',
        f'generator: {json.dumps(SCRIPT_NAME, ensure_ascii=False)}',
        f'provider: {json.dumps(provider, ensure_ascii=False)}',
        "---",
        "",
        f"# {title}",
        "",
        "## Câu hỏi và trả lời",
        "",
    ]
    for question, answer_lines in qas:
        lines.append(f"**Q:** {question}")
        if answer_lines:
            lines.append(f"**A:** - {answer_lines[0]}")
            for extra_line in answer_lines[1:]:
                lines.append(f"- {extra_line}")
        else:
            lines.append("**A:** - Hiện tại chưa có thông tin này.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def try_init_gemini(model_name: str):
    try:
        from dotenv import load_dotenv  # type: ignore
        import google.generativeai as genai  # type: ignore
    except Exception as error:
        raise RuntimeError(f"Gemini dependencies are unavailable: {error}") from error

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in environment or .env.")

    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        model_name,
        generation_config={
            "temperature": 0.2,
            "top_p": 0.9,
            "max_output_tokens": 1600,
        },
    )


def trim_context(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[Context truncated]"


def build_llm_context_for_file(doc: ContextDoc) -> str:
    metadata_lines = []
    for key in (
        "title",
        "inferred_group",
        "inferred_topic",
        "inferred_document_type",
        "inferred_years",
        "inferred_school_years",
        "document_status",
        "ocr_required",
    ):
        if key in doc.metadata:
            metadata_lines.append(f"- {key}: {doc.metadata[key]}")
    lines = [
        f"FILE: {doc.relative_path.as_posix()}",
        *metadata_lines,
        "",
        "BODY:",
        doc.body.strip(),
    ]
    return "\n".join(lines).strip()


def build_llm_context_for_group(group_name: str, docs: list[ContextDoc]) -> str:
    sections = [f"GROUP: {group_name}", ""]
    for doc in docs:
        sections.append(f"### {doc.title}")
        sections.append(build_llm_context_for_file(doc))
        sections.append("")
    return "\n".join(sections).strip()


def generate_with_gemini(
    model,
    title: str,
    context_text: str,
    question_limit: int,
) -> str:
    prompt = f"""Ban dang tao du lieu QA tieng Viet cho chatbot.

Muc tieu:
- Tao khoang {question_limit} cap hoi-dap.
- Chi duoc dung thong tin xuat hien trong context.
- Khong duoc bịa số liệu, tên cơ quan, điều khoản hay mốc thời gian.
- Neu context chi co metadata hoac body chua day du, van tao QA muc tong quan va noi ro can OCR/bo sung context khi phu hop.
- Cau tra loi ngan gon, de quan ly, uu tien dang bullet.

Bat buoc output dung markdown theo format sau:

## Câu hỏi và trả lời

**Q:** ...
**A:** - ...
- ...

**Q:** ...
**A:** - ...

Khong them giai thich ngoai phan markdown.

TITLE:
{title}

CONTEXT:
{context_text}
"""
    response = model.generate_content(prompt)
    text = (getattr(response, "text", "") or "").strip()
    if "## Câu hỏi và trả lời" not in text:
        raise RuntimeError("Gemini response did not return the expected QA markdown section.")
    return text


def build_output_path(
    output_root: Path,
    group_key: str,
    docs: list[ContextDoc],
    mode: str,
) -> Path:
    if mode == "file":
        return output_root / docs[0].relative_path
    return output_root / f"{slugify(group_key)}.md"


def ensure_md_suffix(path: Path) -> Path:
    return path if path.suffix.lower() == ".md" else path.with_suffix(".md")


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_root = Path(args.output).resolve()

    if not input_path.exists():
        safe_print(f"Input path does not exist: {input_path}", error=True)
        return 1

    input_root, docs = collect_input_docs(input_path, include_pending=args.include_pending)
    if not docs:
        safe_print("No markdown context files were found.", error=True)
        return 1

    grouped_items = group_docs(docs, mode=args.mode)
    output_root.mkdir(parents=True, exist_ok=True)

    provider = args.provider
    model = None
    if provider in ("auto", "gemini"):
        try:
            model = try_init_gemini(args.model)
            provider = "gemini"
        except Exception as error:
            if args.provider == "gemini":
                safe_print(str(error), error=True)
                return 2
            provider = "heuristic"
            if args.verbose:
                safe_print(f"Gemini unavailable, falling back to heuristic mode: {error}")

    written = 0
    skipped = 0

    for group_key, group_docs_list in grouped_items:
        output_path = ensure_md_suffix(build_output_path(output_root, group_key, group_docs_list, args.mode))
        if output_path.exists() and not args.force:
            skipped += 1
            if args.verbose:
                safe_print(f"Skip existing: {output_path}")
            continue

        if provider == "gemini" and model is not None:
            title = group_docs_list[0].title if args.mode == "file" else f"QA - {group_key}"
            context_text = (
                build_llm_context_for_file(group_docs_list[0])
                if args.mode == "file"
                else build_llm_context_for_group(group_key, group_docs_list)
            )
            context_text = trim_context(context_text, args.max_context_chars)
            qa_section = generate_with_gemini(model, title=title, context_text=context_text, question_limit=args.questions_per_item)
            qa_markdown = "\n".join(
                [
                    "---",
                    f'title: {json.dumps(title, ensure_ascii=False)}',
                    f'source: {json.dumps(group_key, ensure_ascii=False)}',
                    f'generated_at: {json.dumps(datetime.now().astimezone().isoformat(timespec="seconds"), ensure_ascii=False)}',
                    f'generator: {json.dumps(SCRIPT_NAME, ensure_ascii=False)}',
                    f'provider: {json.dumps("gemini", ensure_ascii=False)}',
                    "---",
                    "",
                    f"# {title}",
                    "",
                    qa_section.strip(),
                    "",
                ]
            ).rstrip() + "\n"
        else:
            if args.mode == "file":
                doc = group_docs_list[0]
                qas = build_heuristic_qas(doc, question_limit=args.questions_per_item)
                qa_markdown = format_qa_markdown(
                    title=f"QA - {doc.title}",
                    source_label=doc.relative_path.as_posix(),
                    provider="heuristic",
                    qas=qas,
                )
            else:
                qas = build_group_heuristic_qas(group_key, group_docs_list, question_limit=args.questions_per_item)
                qa_markdown = format_qa_markdown(
                    title=f"QA - {group_key}",
                    source_label=group_key,
                    provider="heuristic",
                    qas=qas,
                )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(qa_markdown, encoding="utf-8")
        written += 1
        if args.verbose:
            safe_print(f"Wrote: {output_path}")

    safe_print("")
    safe_print("Summary")
    safe_print(f"- Groups/files processed: {len(grouped_items)}")
    safe_print(f"- Files written: {written}")
    safe_print(f"- Skipped existing: {skipped}")
    safe_print(f"- Provider used: {provider}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
