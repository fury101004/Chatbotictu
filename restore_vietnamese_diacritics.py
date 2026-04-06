#!/usr/bin/env python
# Usage:
#   python restore_vietnamese_diacritics.py --input data/qa_generated --in-place --provider repair
#   python restore_vietnamese_diacritics.py --input clean_data --output data/clean_data_fixed --provider auto --force
#   python restore_vietnamese_diacritics.py --input "data/qa_generated/Cac Van Ban Phap Quy" --provider gemini --verbose

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


SCRIPT_NAME = "restore_vietnamese_diacritics.py"
MOJIBAKE_MARKERS = ("Ã", "Ä", "Å", "Æ", "Â", "áº", "á»", "â€", "â€™", "â€œ", "â€”", "Ð", "Ñ")
ACCENTABLE_FRONTMATTER_KEYS = {
    "title",
    "inferred_group",
    "inferred_topic",
    "inferred_document_type",
    "summary",
    "source",
}
PATH_LIKE_KEYS = {"source_pdf", "source_relative_path"}
COMMON_PHRASE_REPLACEMENTS = {
    "Tai lieu": "Tài liệu",
    "tai lieu": "tài liệu",
    "Tài liệu nay": "Tài liệu này",
    "tài liệu nay": "tài liệu này",
    "thuoc nhom": "thuộc nhóm",
    "thuộc nhóm nao": "thuộc nhóm nào",
    "thuoc": "thuộc",
    "nhom": "nhóm",
    "Chu de": "Chủ đề",
    "chu de": "chủ đề",
    "chinh": "chính",
    "dang duoc": "đang được",
    "gan la": "gán là",
    "duoc xep vao nhom": "được xếp vào nhóm",
    "duoc xep vao nhóm": "được xếp vào nhóm",
    "duoc": "được",
    "vao": "vào",
    "Day la loai van ban gi?": "Đây là loại văn bản gì?",
    "Day la loai": "Đây là loại",
    "Đây là loại văn bản gi?": "Đây là loại văn bản gì?",
    "duoc nhan dang gan dung la": "được nhận dạng gần đúng là",
    "duoc nhan dang": "được nhận dạng",
    "nhan dang": "nhận dạng",
    "gan dung": "gần đúng",
    "van ban": "văn bản",
    "Van ban": "Văn bản",
    "Ten file hien tai la": "Tên file hiện tại là",
    "Ten file hiện tại la": "Tên file hiện tại là",
    "Tai lieu nay ap dung cho nam nao hoac giai doan nao?": "Tài liệu này áp dụng cho năm nào hoặc giai đoạn nào?",
    "Tài liệu nay ap dung cho nam nao hoac giai doan nao?": "Tài liệu này áp dụng cho năm nào hoặc giai đoạn nào?",
    "ap dung": "áp dụng",
    "hoac": "hoặc",
    "Noi dung tom tat hien tai cho thay dieu gi?": "Nội dung tóm tắt hiện tại cho thấy điều gì?",
    "Noi dung tom tat hiện tại cho thay dieu gi?": "Nội dung tóm tắt hiện tại cho thấy điều gì?",
    "Noi dung tom tat": "Nội dung tóm tắt",
    "cho thay dieu gi?": "cho thấy điều gì?",
    "Tinh trang du lieu cua tai lieu nay hien tai ra sao?": "Tình trạng dữ liệu của tài liệu này hiện tại ra sao?",
    "Tinh trang dữ liệu cua tài liệu nay hiện tại ra sao?": "Tình trạng dữ liệu của tài liệu này hiện tại ra sao?",
    "Tinh trang": "Tình trạng",
    "Can lam gi neu muon chatbot tra loi tot hon tu tai lieu nay?": "Cần làm gì nếu muốn chatbot trả lời tốt hơn từ tài liệu này?",
    "Can lam gi neu muon chatbot trả lời tot hon tu tài liệu nay?": "Cần làm gì nếu muốn chatbot trả lời tốt hơn từ tài liệu này?",
    "Can lam gi neu muon": "Cần làm gì nếu muốn",
    "Can bo sung": "Cần bổ sung",
    "Neu tai lieu": "Nếu tài liệu",
    "Neu tài liệu": "Nếu tài liệu",
    "tu tài liệu này": "từ tài liệu này",
    "la scan": "là scan",
    "scan hoac": "scan hoặc",
    "body con thieu": "body còn thiếu",
    "nen OCR": "nên OCR",
    "quy trinh": "quy trình",
    "tao QA": "tạo QA",
    "chay lai": "chạy lại",
    "ro rang": "rõ ràng",
    "sach va day du": "sạch và đầy đủ",
    "sạch và đầy đủ hon": "sạch và đầy đủ hơn",
    "tra loi": "trả lời",
    "du lieu": "dữ liệu",
    "dữ liệu cua": "dữ liệu của",
    "hien tai": "hiện tại",
    "hiện tại la": "hiện tại là",
    "ra sao": "ra sao",
    "Cac nam duoc nhan thay trong context": "Các năm được nhận thấy trong context",
    "Thong tu": "Thông tư",
    "thong tu": "thông tư",
    "Quyet dinh": "Quyết định",
    "quyet dinh": "quyết định",
    "Thong bao": "Thông báo",
    "thong bao": "thông báo",
    "Cong van": "Công văn",
    "cong van": "công văn",
    "Ke hoach": "Kế hoạch",
    "ke hoach": "kế hoạch",
    "quy dinh": "quy định",
    "noi bo": "nội bộ",
    "hanh chinh": "hành chính",
    "hanh chính": "hành chính",
    "den": "đến",
    "đến nam": "đến năm",
    "van de": "vấn đề",
    "nam hoc": "năm học",
    "nhung trang nao": "những trang nào",
    "ve email": "về email",
    "va quy dinh su dung email": "và quy định sử dụng email",
    "va": "và",
    "su dung": "sử dụng",
    "gần đúng la": "gần đúng là",
    "gi?": "gì?",
    "nao?": "nào?",
    "nam nao": "năm nào",
    "giai doan nao": "giai đoạn nào",
    "tot hon": "tốt hơn",
    "huong dan": "hướng dẫn",
    "lien quan": "liên quan",
    "Dua tren ten file va cau truc thu muc, no co kha nang la": "Dựa trên tên file và cấu trúc thư mục, nó có khả năng là",
    "Dua tren ten file và cau truc thu muc, no co kha nang la": "Dựa trên tên file và cấu trúc thư mục, nó có khả năng là",
    "Phan body hien tai duoc tao tu metadata va ten file, chua phai noi dung OCR day du.": "Phần body hiện tại được tạo từ metadata và tên file, chưa phải nội dung OCR đầy đủ.",
    "Phan body hiện tại duoc tao tu metadata va ten file, chua phai noi dung OCR day du.": "Phần body hiện tại được tạo từ metadata và tên file, chưa phải nội dung OCR đầy đủ.",
    "Phan body hiện tại được tao tu metadata và ten file, chua phai noi dung OCR day du.": "Phần body hiện tại được tạo từ metadata và tên file, chưa phải nội dung OCR đầy đủ.",
    "Tài liệu nay thuộc nhóm nao va lien quan den van de gi?": "Tài liệu này thuộc nhóm nào và liên quan đến vấn đề gì?",
    "lien quan den van de gi?": "liên quan đến vấn đề gì?",
    "Thong bao nay ap dung cho nam hoc hoac giai doan nao?": "Thông báo này áp dụng cho năm học hoặc giai đoạn nào?",
    "Thông báo nay ap dung cho nam hoc hoac giai đoạn nào?": "Thông báo này áp dụng cho năm học hoặc giai đoạn nào?",
    "Thông báo nay": "Thông báo này",
    "Văn bản nay": "Văn bản này",
    "Van ban nay ap dung cho nam hoc hoac giai doan nao?": "Văn bản này áp dụng cho năm học hoặc giai đoạn nào?",
    "Can OCR them nhung trang nao de co du noi dung cho tai lieu nay?": "Cần OCR thêm những trang nào để có đủ nội dung cho tài liệu này?",
    "Can OCR them nhung trang nao de co du noi dung cho tài liệu nay?": "Cần OCR thêm những trang nào để có đủ nội dung cho tài liệu này?",
    "Can OCR them": "Cần OCR thêm",
    "de co du noi dung cho tài liệu này?": "để có đủ nội dung cho tài liệu này?",
    "Van ban nay lien quan den nam": "Văn bản này liên quan đến năm",
    "nhu the nao?": "như thế nào?",
    "nhu the nào?": "như thế nào?",
    "Bao hiem y te": "Bảo hiểm y tế",
    "Van ban phap quy": "Văn bản pháp quy",
    "Van ban quan ly noi bo": "Văn bản quản lý nội bộ",
    "Xet diem ren luyen": "Xét điểm rèn luyện",
    "Hoc bong": "Học bổng",
    "Tot nghiep": "Tốt nghiệp",
    "Nam hoc": "Năm học",
    "Nguoi hoc": "Người học",
    "Cau hoi va tra loi": "Câu hỏi và trả lời",
    "Document status hien tai la": "Document status hiện tại là",
    "Body source dang la": "Body source đang là",
    "Ti le trang co text su dung duoc la": "Tỉ lệ trang có text sử dụng được là",
}


@dataclass
class ProcessResult:
    changed: bool
    mojibake_fixed: bool
    diacritics_added: bool
    text: str


def safe_print(message: str = "", *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    encoding = stream.encoding or "utf-8"
    try:
        print(message, file=stream)
    except UnicodeEncodeError:
        fallback = message.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(fallback, file=stream)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair mojibake and optionally restore Vietnamese diacritics in markdown files.")
    parser.add_argument("--input", default="data/qa_generated", help="Input markdown file or directory.")
    parser.add_argument("--output", help="Output directory. Omit when using --in-place.")
    parser.add_argument("--in-place", action="store_true", help="Write changes back to the original files.")
    parser.add_argument("--provider", choices=("auto", "repair", "gemini"), default="auto", help="Repair provider.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output files.")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N markdown files.")
    parser.add_argument("--verbose", action="store_true", help="Print detailed progress logs.")
    parser.add_argument("--model", default="gemini-2.5-flash-lite", help="Gemini model name when provider uses Gemini.")
    parser.add_argument("--max-chars", type=int, default=6000, help="Maximum characters per Gemini chunk.")
    return parser.parse_args()


def collect_markdown_files(input_path: Path) -> tuple[Path, list[Path]]:
    if input_path.is_file():
        return input_path.parent, [input_path]
    files = sorted(input_path.rglob("*.md"), key=lambda item: str(item).lower())
    return input_path, files


def count_vietnamese_chars(text: str) -> int:
    return sum(1 for char in text if char in "ăâđêôơưĂÂĐÊÔƠƯáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵÁÀẢÃẠẮẰẲẴẶẤẦẨẪẬÉÈẺẼẸẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴ")


def mojibake_penalty(text: str) -> int:
    return sum(text.count(marker) for marker in MOJIBAKE_MARKERS) * 40


def text_quality_score(text: str) -> int:
    return (
        count_vietnamese_chars(text) * 4
        + sum(1 for char in text if char.isalpha())
        + len(re.findall(r"\w+", text, flags=re.UNICODE)) * 3
        - mojibake_penalty(text)
    )


def contains_mojibake(text: str) -> bool:
    return any(marker in text for marker in MOJIBAKE_MARKERS)


def try_repair_roundtrip(text: str, encoding_name: str) -> str:
    try:
        return text.encode(encoding_name, errors="ignore").decode("utf-8", errors="ignore")
    except Exception:
        return text


def fix_mojibake(text: str) -> tuple[str, bool]:
    current = text
    changed = False

    for _ in range(3):
        candidates = [
            current,
            try_repair_roundtrip(current, "latin1"),
            try_repair_roundtrip(current, "cp1252"),
            try_repair_roundtrip(current, "cp1258"),
        ]
        best = max(candidates, key=text_quality_score)
        if best == current:
            break
        current = best
        changed = True

    return current, changed


def split_front_matter(text: str) -> tuple[str, str, str]:
    if not text.startswith("---\n"):
        return "", "", text
    end_marker = text.find("\n---\n", 4)
    if end_marker == -1:
        return "", "", text
    return text[:4], text[4:end_marker], text[end_marker + 5 :]


def looks_like_prose_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith(("```", "    ", "\t")):
        return False
    if re.match(r"^[A-Za-z0-9_.\\/:-]+$", stripped):
        return False
    letters = sum(1 for char in stripped if char.isalpha())
    spaces = stripped.count(" ")
    return letters >= 6 and spaces >= 1


def looks_like_unaccented_vietnamese(line: str) -> bool:
    stripped = line.strip()
    if not looks_like_prose_line(stripped):
        return False
    if count_vietnamese_chars(stripped) > 0:
        return False
    lowered = stripped.lower()
    signal_phrases = [
        "tai lieu", "thuoc nhom", "chu de", "thong bao", "quyet dinh", "thong tu", "hoc bong",
        "tot nghiep", "ren luyen", "bao hiem", "nam hoc", "nguoi hoc", "hoi", "tra loi",
        "dieu gi", "hien tai", "can lam gi", "van ban", "chu de", "du lieu", "noi dung",
        "quy dinh", "ke hoach", "cong van",
    ]
    return any(phrase in lowered for phrase in signal_phrases)


def repair_common_phrases(text: str) -> tuple[str, bool]:
    changed = False
    output_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not re.match(r"^[A-Za-z0-9_.\\/:-]+$", stripped):
            original_line = line
            for source, target in COMMON_PHRASE_REPLACEMENTS.items():
                escaped = re.escape(source)
                if source[:1].isalnum() and source[-1:].isalnum():
                    pattern = rf"\b{escaped}\b"
                else:
                    pattern = escaped
                line = re.sub(pattern, target, line)
            if line != original_line:
                changed = True
        output_lines.append(line)
    rebuilt = "\n".join(output_lines)
    if text.endswith("\n") and not rebuilt.endswith("\n"):
        rebuilt += "\n"
    return rebuilt, changed


def maybe_init_gemini(model_name: str):
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
        generation_config={"temperature": 0.1, "top_p": 0.9, "max_output_tokens": 1600},
    )


def chunk_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n\n", 0, max_chars)
        if split_at < max_chars // 2:
            split_at = remaining.rfind("\n", 0, max_chars)
        if split_at < max_chars // 2:
            split_at = max_chars
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    return chunks


def accent_chunk_with_gemini(model, text: str) -> str:
    prompt = f"""Hãy khôi phục dấu tiếng Việt cho văn bản Markdown dưới đây.

Quy tắc:
- Chỉ thêm dấu và sửa lỗi mã hóa tiếng Việt nếu có.
- Giữ nguyên Markdown, bullet, heading, Q/A, số liệu, đường dẫn, mã.
- Không thêm ý mới, không bịa thông tin, không dịch sang ngôn ngữ khác.
- Nếu một dòng đã đúng rồi thì giữ nguyên.

Văn bản:
{text}
"""
    response = model.generate_content(prompt)
    output = (getattr(response, "text", "") or "").strip()
    return output or text


def accent_body_with_gemini(body: str, model, max_chars: int) -> tuple[str, bool]:
    if not any(looks_like_unaccented_vietnamese(line) or contains_mojibake(line) for line in body.splitlines()):
        return body, False

    changed = False
    chunks = chunk_text(body, max_chars=max_chars)
    repaired_chunks: list[str] = []
    for chunk in chunks:
        repaired = accent_chunk_with_gemini(model, chunk)
        if repaired != chunk:
            changed = True
        repaired_chunks.append(repaired)
    return "\n\n".join(part.strip("\n") for part in repaired_chunks).strip() + ("\n" if body.endswith("\n") else ""), changed


def repair_front_matter(raw_meta: str, provider: str, model, max_chars: int) -> tuple[str, bool, bool]:
    if not raw_meta:
        return raw_meta, False, False

    mojibake_fixed = False
    diacritics_added = False
    output_lines: list[str] = []

    for line in raw_meta.splitlines():
        if ":" not in line:
            fixed_line, fixed = fix_mojibake(line)
            mojibake_fixed |= fixed
            output_lines.append(fixed_line)
            continue

        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.lstrip()

        fixed_value, fixed = fix_mojibake(value)
        mojibake_fixed |= fixed

        should_accent = provider == "gemini" and key in ACCENTABLE_FRONTMATTER_KEYS and looks_like_unaccented_vietnamese(fixed_value)
        if should_accent and model is not None:
            accented, changed = accent_body_with_gemini(fixed_value, model, max_chars=max_chars)
            fixed_value = accented.rstrip("\n")
            diacritics_added |= changed

        output_lines.append(f"{key}: {fixed_value}")

    return "\n".join(output_lines), mojibake_fixed, diacritics_added


def process_markdown_text(text: str, provider: str, model, max_chars: int) -> ProcessResult:
    prefix, raw_meta, body = split_front_matter(text)

    fixed_meta, meta_mojibake, meta_diacritics = repair_front_matter(raw_meta, provider, model, max_chars)
    fixed_body, body_mojibake = fix_mojibake(body)
    fixed_meta, meta_phrase_fix = repair_common_phrases(fixed_meta)
    fixed_body, body_phrase_fix = repair_common_phrases(fixed_body)

    body_diacritics = False
    if provider == "gemini" and model is not None:
        fixed_body, body_diacritics = accent_body_with_gemini(fixed_body, model, max_chars=max_chars)

    if prefix and raw_meta:
        rebuilt = prefix + fixed_meta + "\n---\n" + fixed_body
    else:
        rebuilt = fixed_body

    return ProcessResult(
        changed=rebuilt != text,
        mojibake_fixed=meta_mojibake or body_mojibake,
        diacritics_added=meta_diacritics or body_diacritics or meta_phrase_fix or body_phrase_fix,
        text=rebuilt,
    )


def destination_for(path: Path, input_root: Path, output_root: Path | None, in_place: bool) -> Path:
    if in_place:
        return path
    assert output_root is not None
    return output_root / path.relative_to(input_root)


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    if not input_path.exists():
        safe_print(f"Input path does not exist: {input_path}", error=True)
        return 1

    if args.in_place and args.output:
        safe_print("Use either --in-place or --output, not both.", error=True)
        return 1
    if not args.in_place and not args.output:
        safe_print("Provide --output or use --in-place.", error=True)
        return 1

    input_root, files = collect_markdown_files(input_path)
    if args.limit is not None:
        files = files[: max(args.limit, 0)]
    if not files:
        safe_print("No markdown files found.", error=True)
        return 1

    provider = args.provider
    model = None
    if provider in ("auto", "gemini"):
        try:
            model = maybe_init_gemini(args.model)
            provider = "gemini"
        except Exception as error:
            if args.provider == "gemini":
                safe_print(str(error), error=True)
                return 2
            provider = "repair"
            if args.verbose:
                safe_print(f"Gemini unavailable, using local repair only: {error}")

    output_root = None if args.in_place else Path(args.output).resolve()
    if output_root is not None:
        output_root.mkdir(parents=True, exist_ok=True)

    changed_count = 0
    skipped_existing = 0
    mojibake_count = 0
    diacritics_count = 0

    for path in files:
        target = destination_for(path, input_root, output_root, args.in_place)
        if target.exists() and not args.force and not args.in_place:
            skipped_existing += 1
            if args.verbose:
                safe_print(f"Skip existing: {target}")
            continue

        original = path.read_text(encoding="utf-8", errors="ignore")
        result = process_markdown_text(original, provider=provider, model=model, max_chars=args.max_chars)

        if not args.in_place and target.parent:
            target.parent.mkdir(parents=True, exist_ok=True)

        if result.changed or args.force or args.in_place:
            target.write_text(result.text, encoding="utf-8")

        changed_count += int(result.changed)
        mojibake_count += int(result.mojibake_fixed)
        diacritics_count += int(result.diacritics_added)

        if args.verbose:
            status_bits = []
            if result.mojibake_fixed:
                status_bits.append("mojibake_fixed")
            if result.diacritics_added:
                status_bits.append("diacritics_added")
            if not status_bits:
                status_bits.append("no_change")
            safe_print(f"Processed: {target} [{', '.join(status_bits)}]")

    safe_print("")
    safe_print("Summary")
    safe_print(f"- Files scanned: {len(files)}")
    safe_print(f"- Files changed: {changed_count}")
    safe_print(f"- Files with mojibake fixed: {mojibake_count}")
    safe_print(f"- Files with diacritics added by model: {diacritics_count}")
    safe_print(f"- Skipped existing: {skipped_existing}")
    safe_print(f"- Provider used: {provider}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
