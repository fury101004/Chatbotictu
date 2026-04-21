#!/usr/bin/env python
# Usage:
#   python tools/data_pipeline/convert_datapdf_to_md.py
#   python tools/data_pipeline/convert_datapdf_to_md.py --input datapdf --output clean_data --force
#   python tools/data_pipeline/convert_datapdf_to_md.py --limit 2 --verbose
#   python tools/data_pipeline/convert_datapdf_to_md.py --ocr auto --ocr-lang vie+eng --ocr-psm 6,4,11 --force
#   python tools/data_pipeline/convert_datapdf_to_md.py --debug-ocr --force

from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable


SCRIPT_NAME = "convert_datapdf_to_md.py"
DEFAULT_INPUT_DIR = "datapdf"
COMMON_INPUT_DIR_CANDIDATES = (
    DEFAULT_INPUT_DIR,
    "data/pdfs",
    "data/pdf",
    "pdfs",
    "pdf",
    "uploads",
    "data/uploads",
    "data/rag_uploads",
    "docs/pdfs",
    "docs/pdf",
)
LOW_TEXT_SCORE = 120
GOOD_TEXT_SCORE = 320
SCAN_IMAGE_RATIO = 0.60


@dataclass
class Extractor:
    name: str
    extract: Callable[[Path], tuple[list[str], int]]


@dataclass
class ExtractedDocument:
    method: str
    pages: list[str]
    page_count: int


@dataclass
class PageProbe:
    image_count: int = 0
    largest_image_ratio: float = 0.0


@dataclass
class OCRResult:
    text: str
    score: int
    method: str


@dataclass
class OCREngine:
    name: str
    ocr_page: Callable[[Path, int, str, int, list[int], Path | None], OCRResult]


@dataclass
class PageInsight:
    index: int
    text: str
    method: str
    score: int
    image_count: int
    largest_image_ratio: float
    kind: str
    source_methods: list[str] = field(default_factory=list)
    ocr_attempted: bool = False
    ocr_used: bool = False


@dataclass
class Summary:
    total_pdfs: int = 0
    converted: int = 0
    pending_ocr: int = 0
    skipped_existing: int = 0
    needs_ocr: int = 0
    errors: int = 0
    non_pdf_skipped: int = 0


def safe_print(message: str = "", *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    encoding = stream.encoding or "utf-8"
    try:
        print(message, file=stream)
    except UnicodeEncodeError:
        fallback = message.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(fallback, file=stream)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert PDFs into Markdown with best-effort full text extraction."
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT_DIR,
        help=(
            "Input directory containing PDFs. Defaults to auto-detecting common folders and "
            f"falls back to '{DEFAULT_INPUT_DIR}'."
        ),
    )
    parser.add_argument("--output", default="clean_data", help="Output directory for Markdown files.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing Markdown files.")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N PDF files.")
    parser.add_argument("--verbose", action="store_true", help="Print detailed progress logs.")
    parser.add_argument(
        "--ocr",
        choices=("off", "auto", "force"),
        default="auto",
        help="OCR mode for scan-like pages.",
    )
    parser.add_argument(
        "--ocr-lang",
        default="vie+eng",
        help="OCR language pack passed to Tesseract. Example: vie+eng",
    )
    parser.add_argument(
        "--ocr-dpi",
        type=int,
        default=300,
        help="Render DPI for OCR page images.",
    )
    parser.add_argument(
        "--ocr-psm",
        default="6,4,11",
        help="Comma-separated Tesseract PSM values to try. Example: 6,4,11",
    )
    parser.add_argument(
        "--debug-ocr",
        action="store_true",
        help="Save OCR preprocessed page images under the output directory.",
    )
    parser.add_argument(
        "--incomplete-policy",
        choices=("pending", "keep", "skip"),
        default="pending",
        help="How to handle documents that are not clean enough after extraction.",
    )
    parser.add_argument(
        "--pending-dir-name",
        default="_ocr_pending",
        help="Subdirectory under output used for incomplete documents when policy=pending.",
    )
    return parser.parse_args()


def parse_ocr_psm(raw_value: str) -> list[int]:
    values: list[int] = []
    for piece in raw_value.split(","):
        piece = piece.strip()
        if not piece:
            continue
        values.append(int(piece))
    return values or [6]


def resolve_user_path(raw_path: str, base_dir: Path) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def default_input_candidates(base_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()

    for raw_path in COMMON_INPUT_DIR_CANDIDATES:
        candidate = resolve_user_path(raw_path, base_dir)
        normalized = str(candidate).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(candidate)

    return candidates


def directory_contains_pdf(input_dir: Path) -> bool:
    try:
        return any(input_dir.rglob("*.pdf"))
    except Exception:
        return False


def resolve_input_dir(raw_input: str, base_dir: Path) -> tuple[Path | None, str | None, bool]:
    requested_dir = resolve_user_path(raw_input, base_dir)
    using_default_input = raw_input == DEFAULT_INPUT_DIR

    if requested_dir.exists():
        if not requested_dir.is_dir():
            return None, f"Input path is not a directory: {requested_dir}", False
        return requested_dir, None, False

    if not using_default_input:
        return None, f"Input directory does not exist: {requested_dir}", False

    for candidate in default_input_candidates(base_dir):
        if not candidate.exists() or not candidate.is_dir():
            continue
        if directory_contains_pdf(candidate):
            return candidate, None, True

    checked_locations = "\n".join(f"  - {candidate}" for candidate in default_input_candidates(base_dir))
    message = (
        f"Input directory does not exist: {requested_dir}\n"
        "No fallback directory containing PDF files was found.\n"
        f"Checked common locations under {base_dir}:\n"
        f"{checked_locations}\n"
        f"Create '{DEFAULT_INPUT_DIR}' in the project root or run:\n"
        f"  python {SCRIPT_NAME} --input PATH_TO_YOUR_PDFS"
    )
    return None, message, False


def discover_extractors() -> list[Extractor]:
    extractors: list[Extractor] = []

    try:
        import fitz  # type: ignore

        def extract_with_fitz(pdf_path: Path) -> tuple[list[str], int]:
            document = fitz.open(pdf_path)
            try:
                pages = [(page.get_text("text", sort=True) or "") for page in document]
                return pages, document.page_count
            finally:
                document.close()

        extractors.append(Extractor(name="PyMuPDF", extract=extract_with_fitz))
    except Exception:
        pass

    try:
        import pdfplumber  # type: ignore

        def extract_with_pdfplumber(pdf_path: Path) -> tuple[list[str], int]:
            with pdfplumber.open(str(pdf_path)) as pdf:
                pages = []
                for page in pdf.pages:
                    text = page.extract_text(layout=True) or page.extract_text() or ""
                    pages.append(text)
                return pages, len(pdf.pages)

        extractors.append(Extractor(name="pdfplumber", extract=extract_with_pdfplumber))
    except Exception:
        pass

    try:
        from pypdf import PdfReader  # type: ignore

        def extract_with_pypdf(pdf_path: Path) -> tuple[list[str], int]:
            reader = PdfReader(str(pdf_path))
            if reader.is_encrypted:
                reader.decrypt("")
            pages = []
            for page in reader.pages:
                try:
                    text = page.extract_text(extraction_mode="layout") or page.extract_text() or ""
                except TypeError:
                    text = page.extract_text() or ""
                pages.append(text)
            return pages, len(reader.pages)

        extractors.append(Extractor(name="pypdf", extract=extract_with_pypdf))
    except Exception:
        pass

    try:
        from PyPDF2 import PdfReader  # type: ignore

        def extract_with_pypdf2(pdf_path: Path) -> tuple[list[str], int]:
            reader = PdfReader(str(pdf_path))
            if reader.is_encrypted:
                reader.decrypt("")
            pages = [(page.extract_text() or "") for page in reader.pages]
            return pages, len(reader.pages)

        extractors.append(Extractor(name="PyPDF2", extract=extract_with_pypdf2))
    except Exception:
        pass

    return extractors


def probe_pdf_pages(pdf_path: Path) -> list[PageProbe]:
    try:
        import fitz  # type: ignore

        document = fitz.open(pdf_path)
        try:
            probes: list[PageProbe] = []
            for page in document:
                page_area = max(float(page.rect.width * page.rect.height), 1.0)
                largest_ratio = 0.0
                images = page.get_images(full=True)
                for image_info in images:
                    xref = image_info[0]
                    try:
                        rects = page.get_image_rects(xref)
                    except Exception:
                        rects = []
                    for rect in rects:
                        rect_area = max(float(rect.width * rect.height), 0.0)
                        largest_ratio = max(largest_ratio, rect_area / page_area)
                if images and largest_ratio == 0.0:
                    largest_ratio = 1.0
                probes.append(PageProbe(image_count=len(images), largest_image_ratio=largest_ratio))
            return probes
        finally:
            document.close()
    except Exception:
        pass

    try:
        from PyPDF2 import PdfReader  # type: ignore

        reader = PdfReader(str(pdf_path))
        probes = []
        for page in reader.pages:
            image_count = len(page.images) if hasattr(page, "images") else 0
            largest_ratio = 1.0 if image_count else 0.0
            probes.append(PageProbe(image_count=image_count, largest_image_ratio=largest_ratio))
        return probes
    except Exception:
        return []


def discover_ocr_engine() -> OCREngine | None:
    tesseract_path = shutil.which("tesseract")
    if not tesseract_path:
        return None

    try:
        import fitz  # type: ignore
        import pytesseract  # type: ignore
        from PIL import Image, ImageFilter, ImageOps  # type: ignore
    except Exception:
        return None

    def save_debug_image(image, debug_dir: Path | None, stem: str) -> None:
        if debug_dir is None:
            return
        debug_dir.mkdir(parents=True, exist_ok=True)
        image.save(debug_dir / f"{stem}.png")

    def preprocess_variants(image):
        grayscale = ImageOps.grayscale(image)
        grayscale = ImageOps.autocontrast(grayscale)
        sharpened = grayscale.filter(ImageFilter.SHARPEN)
        threshold = sharpened.point(lambda value: 255 if value > 180 else 0, mode="1").convert("L")
        return [
            ("gray", grayscale),
            ("sharpen", sharpened),
            ("binary", threshold),
        ]

    def ocr_page_with_tesseract(
        pdf_path: Path,
        page_index: int,
        lang: str,
        dpi: int,
        psm_values: list[int],
        debug_dir: Path | None,
    ) -> OCRResult:
        document = fitz.open(pdf_path)
        try:
            page = document.load_page(page_index)
            zoom = max(dpi, 72) / 72.0
            matrix = fitz.Matrix(zoom, zoom)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            base_image = Image.open(io.BytesIO(pixmap.tobytes("png")))
        finally:
            document.close()

        page_stem = f"page_{page_index + 1:04d}"
        save_debug_image(base_image, debug_dir, f"{page_stem}_render")

        best_text = ""
        best_score = -1
        best_method = "OCR"

        for variant_name, variant in preprocess_variants(base_image):
            save_debug_image(variant, debug_dir, f"{page_stem}_{variant_name}")
            for psm in psm_values:
                config = f"--oem 3 --psm {psm}"
                try:
                    raw_text = pytesseract.image_to_string(variant, lang=lang, config=config) or ""
                except Exception:
                    continue
                cleaned = clean_page_text(raw_text)
                score = text_score(cleaned)
                if score > best_score:
                    best_text = cleaned
                    best_score = score
                    best_method = f"OCR[{variant_name},psm={psm}]"

        return OCRResult(text=best_text, score=max(best_score, 0), method=best_method)

    return OCREngine(name=f"Tesseract ({tesseract_path})", ocr_page=ocr_page_with_tesseract)


def scan_input_files(input_dir: Path) -> tuple[list[Path], int]:
    pdf_files: list[Path] = []
    non_pdf_count = 0

    for path in input_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".pdf":
            pdf_files.append(path)
        else:
            non_pdf_count += 1

    pdf_files.sort(key=lambda item: str(item).lower())
    return pdf_files, non_pdf_count


def collapse_inline_whitespace(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")
    text = text.replace("\uf0b7", "-")
    text = text.replace("\ufeff", "")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def is_bullet_line(line: str) -> bool:
    return bool(re.match(r"^([\-*•]|[0-9]+[.)]|[A-Za-z][.)])\s+", line))


def looks_like_short_heading(line: str) -> bool:
    if len(line) < 4 or len(line) > 120:
        return False
    if line.endswith((".", ",", ";")):
        return False
    letters = [char for char in line if char.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(1 for char in letters if char.isupper()) / len(letters)
    return upper_ratio >= 0.78


def normalize_bullet(line: str) -> str:
    if re.match(r"^[0-9]+[.)]\s+", line):
        number = re.match(r"^([0-9]+)[.)]\s+(.*)$", line)
        if number:
            return f"{number.group(1)}. {number.group(2).strip()}"
    if re.match(r"^[A-Za-z][.)]\s+", line):
        cleaned = re.sub(r"^[A-Za-z][.)]\s+", "", line).strip()
        return f"- {cleaned}"
    cleaned = re.sub(r"^[-*•]\s+", "", line).strip()
    return f"- {cleaned}"


def should_merge_lines(current_line: str, next_line: str) -> bool:
    if not current_line or not next_line:
        return False
    if is_bullet_line(current_line) or is_bullet_line(next_line):
        return False
    if looks_like_short_heading(current_line) or looks_like_short_heading(next_line):
        return False
    if re.search(r"[.!?:;]$", current_line):
        return False
    if next_line.startswith(("(", "[", "-", "*", "•")):
        return False
    if re.match(r"^[0-9]+[.)]\s+", next_line):
        return False
    if next_line[:1].islower():
        return True
    if current_line.endswith(","):
        return True
    if re.search(r"\b(and|or|of|for|to|with|ve|tai|trong|theo|duoc|la)$", current_line, re.IGNORECASE):
        return True
    return False


def clean_page_text(raw_text: str) -> str:
    raw_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    normalized_lines = [collapse_inline_whitespace(line) for line in raw_text.split("\n")]
    output_lines: list[str] = []
    index = 0

    while index < len(normalized_lines):
        line = normalized_lines[index]
        if not line:
            if output_lines and output_lines[-1] != "":
                output_lines.append("")
            index += 1
            continue

        if is_bullet_line(line):
            output_lines.append(normalize_bullet(line))
            index += 1
            continue

        if looks_like_short_heading(line):
            output_lines.append(f"**{line}**")
            index += 1
            continue

        paragraph = line
        while index + 1 < len(normalized_lines):
            next_line = normalized_lines[index + 1]
            if not next_line:
                break
            if paragraph.endswith("-") and next_line[:1].islower():
                paragraph = paragraph[:-1] + next_line
                index += 1
                continue
            if should_merge_lines(paragraph, next_line):
                paragraph = f"{paragraph} {next_line}"
                index += 1
                continue
            break

        output_lines.append(paragraph.strip())
        index += 1

    compact_lines: list[str] = []
    previous_blank = False
    for line in output_lines:
        is_blank = line == ""
        if is_blank and previous_blank:
            continue
        compact_lines.append(line)
        previous_blank = is_blank

    return "\n".join(compact_lines).strip()


def text_score(text: str) -> int:
    if not text:
        return 0

    letters = sum(1 for char in text if char.isalpha())
    digits = sum(1 for char in text if char.isdigit())
    words = re.findall(r"\w+", text, flags=re.UNICODE)
    non_ascii_letters = sum(1 for char in text if char.isalpha() and ord(char) > 127)
    line_count = len([line for line in text.splitlines() if line.strip()])
    replacement_penalty = text.count("\ufffd") * 80
    weird_control_penalty = sum(1 for char in text if ord(char) < 32 and char not in "\n\t") * 40

    return (
        letters
        + digits
        + (len(words) * 4)
        + (non_ascii_letters * 4)
        + (min(line_count, 40) * 6)
        - replacement_penalty
        - weird_control_penalty
    )


def has_extractable_text(page_texts: Iterable[str]) -> bool:
    return any(text_score(text) >= LOW_TEXT_SCORE for text in page_texts)


def slugify_for_match(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower()
    ascii_text = re.sub(r"[^a-z0-9]+", " ", ascii_text)
    return re.sub(r"\s+", " ", ascii_text).strip()


def clean_context_label(text: str) -> str:
    text = re.sub(r"-\d{8}T\d{6}Z-\d+-\d+$", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -_")


def infer_document_profile(relative_pdf_path: Path, title: str) -> dict[str, object]:
    folder_parts = [clean_context_label(part) for part in relative_pdf_path.parts[:-1]]
    title = clean_context_label(title)
    joined_context = " ".join(folder_parts + [title])
    context_slug = slugify_for_match(joined_context)

    group_map = [
        ("xetdiemrenluyen", "Xet diem ren luyen", "Công văn/ke hoach xet diem ren luyen"),
        ("congvanxettn", "Công văn xet tot nghiep", "Kế hoạch va thông báo xet tot nghiep"),
        ("congvanxethocbong", "Công văn xet hoc bong", "Thông báo va huong dan xet hoc bong"),
        ("congvanvieclam", "Công văn viec lam", "Thông báo viec lam, tuyen dung, hop tac doanh nghiep"),
        ("congvanquyetdinh", "Công văn quyết định", "Quyết định va van ban hanh chinh"),
        ("chedovachinhsach", "Che do va chinh sach", "Ho so va thông báo che do chinh sach"),
        ("cac van quan ly cua co quan chu quan", "Van quan ly cua co quan chu quan", "Van ban dieu hanh tu co quan chu quan"),
        ("cac van ban quan ly noi bo", "Van ban quan ly noi bo", "Quy dinh va quyết định noi bo"),
        ("cac van ban phap quy", "Van ban phap quy", "Thong tu, nghi dinh, quyết định phap quy"),
        ("bao hiem y te", "Bao hiem y te", "Thông báo, huong dan lien quan BHYT"),
        ("congvanveemail", "Công văn ve email", "Thông báo va quy dinh su dung email"),
        ("so tay sinh vien", "So tay sinh vien", "So tay va huong dan cho sinh vien"),
    ]

    group_name = "Tai lieu hanh chinh"
    topic_name = "Van ban quan ly hoc vu va cong tac sinh vien"
    for key, group, topic in group_map:
        if key in context_slug:
            group_name = group
            topic_name = topic
            break

    doc_type_map = [
        ("quyết định", "Quyết định"),
        ("thong tu", "Thong tu"),
        ("nghi dinh", "Nghi dinh"),
        ("ke hoach", "Kế hoạch"),
        ("thông báo", "Thông báo"),
        ("cong van", "Công văn"),
        ("cv ", "Công văn"),
        ("qd ", "Quyết định"),
        ("so tay", "So tay"),
        ("quy che", "Quy che"),
        ("quy dinh", "Quy dinh"),
        ("huong dan", "Huong dan"),
    ]
    document_type = "Van ban"
    for key, label in doc_type_map:
        if key in context_slug:
            document_type = label
            break

    context_for_years = re.sub(r"\d{8}T\d{6}Z", "", joined_context)
    year_matches = re.findall(r"(20\d{2}|19\d{2})", context_for_years)
    years = []
    for year in year_matches:
        if year not in years:
            years.append(year)

    school_year_matches = re.findall(r"(20\d{2}\s*[-./]\s*20\d{2})", joined_context)
    school_years = []
    for school_year in school_year_matches:
        cleaned = re.sub(r"\s+", "", school_year).replace(".", "-").replace("/", "-")
        if cleaned not in school_years:
            school_years.append(cleaned)

    keyword_pool = [
        group_name,
        topic_name,
        document_type,
        title,
        *folder_parts,
        *years,
        *school_years,
    ]
    keywords: list[str] = []
    seen_keywords: set[str] = set()
    for item in keyword_pool:
        item = str(item).strip()
        if not item:
            continue
        lowered = item.lower()
        if lowered in seen_keywords:
            continue
        seen_keywords.add(lowered)
        keywords.append(item)

    suggested_questions = [
        f"Tai lieu nay thuoc nhom nao va lien quan den van de gi?",
        f"{document_type} nay ap dung cho nam hoc hoac giai doan nao?",
        f"Cần OCR thêm những trang nào để có đủ nội dung cho tài liệu này?",
    ]
    if years:
        suggested_questions.append(f"Văn bản này liên quan đến năm {years[0]} như thế nào?")

    summary = (
        f"Tai lieu nay duoc xep vao nhom '{group_name}'. "
        f"Dua tren ten file va cau truc thu muc, no co kha nang la {document_type.lower()} "
        f"thuoc chu de '{topic_name.lower()}'. "
        f"Phan body hien tai duoc tao tu metadata va ten file, chua phai noi dung OCR day du."
    )

    return {
        "group_name": group_name,
        "topic_name": topic_name,
        "document_type": document_type,
        "years": years,
        "school_years": school_years,
        "keywords": keywords[:12],
        "suggested_questions": suggested_questions[:5],
        "summary": summary,
        "folder_parts": folder_parts,
    }


def assess_document_quality(pages: list[PageInsight]) -> dict[str, object]:
    total_pages = len(pages)
    usable_pages = [page.index for page in pages if page.text.strip() and page.score >= LOW_TEXT_SCORE]
    nonempty_pages = [page.index for page in pages if page.text.strip()]
    missing_pages = [page.index for page in pages if not page.text.strip()]
    usable_ratio = (len(usable_pages) / total_pages) if total_pages else 0.0

    if not usable_pages:
        status = "ocr_pending"
    elif len(usable_pages) == total_pages or (usable_ratio >= 0.80 and len(missing_pages) <= 2):
        status = "clean"
    else:
        status = "partial"

    return {
        "status": status,
        "total_pages": total_pages,
        "usable_pages": usable_pages,
        "nonempty_pages": nonempty_pages,
        "missing_pages": missing_pages,
        "usable_ratio": usable_ratio,
    }


def resolve_output_path(
    relative_pdf_path: Path,
    output_dir: Path,
    pending_dir_name: str,
    incomplete_policy: str,
    document_status: str,
) -> tuple[Path | None, bool]:
    output_relative = relative_pdf_path.with_suffix(".md")

    if document_status == "clean" or incomplete_policy == "keep":
        return output_dir / output_relative, False

    if incomplete_policy == "skip":
        return None, True

    return output_dir / pending_dir_name / output_relative, True


def yaml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def extract_documents(pdf_path: Path, extractors: list[Extractor]) -> list[ExtractedDocument]:
    documents: list[ExtractedDocument] = []
    for extractor in extractors:
        try:
            pages, page_count = extractor.extract(pdf_path)
        except Exception:
            continue
        documents.append(ExtractedDocument(method=extractor.name, pages=pages, page_count=page_count))
    return documents


def choose_best_page_text(page_candidates: list[tuple[str, str]]) -> tuple[str, str, int]:
    best_text = ""
    best_method = "none"
    best_score = -1

    for method, raw_text in page_candidates:
        cleaned = clean_page_text(raw_text)
        score = text_score(cleaned)
        if score > best_score:
            best_text = cleaned
            best_method = method
            best_score = score

    return best_text, best_method, max(best_score, 0)


def classify_page(score: int, probe: PageProbe) -> str:
    if probe.image_count > 0 and (probe.largest_image_ratio >= SCAN_IMAGE_RATIO or score < LOW_TEXT_SCORE):
        return "scan_page"
    if probe.image_count > 0 and score >= LOW_TEXT_SCORE:
        return "mixed_page"
    if score >= GOOD_TEXT_SCORE:
        return "digital_text_page"
    if score >= LOW_TEXT_SCORE:
        return "weak_text_page"
    return "weak_text_page"


def should_run_ocr(page: PageInsight, ocr_mode: str) -> bool:
    if ocr_mode == "off":
        return False
    if ocr_mode == "force":
        return True
    if page.kind == "scan_page":
        return True
    if page.kind == "weak_text_page" and page.score < LOW_TEXT_SCORE:
        return True
    return False


def sanitize_debug_name(relative_pdf_path: Path) -> str:
    stem = str(relative_pdf_path.with_suffix(""))
    return re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "document"


def apply_ocr_to_pages(
    pdf_path: Path,
    relative_pdf_path: Path,
    pages: list[PageInsight],
    ocr_engine: OCREngine | None,
    ocr_mode: str,
    ocr_lang: str,
    ocr_dpi: int,
    ocr_psm_values: list[int],
    debug_ocr: bool,
    output_dir: Path,
) -> tuple[list[PageInsight], bool]:
    if ocr_mode == "off":
        return pages, False
    if ocr_engine is None:
        return pages, False

    used_ocr = False
    debug_root = output_dir / "_ocr_debug" / sanitize_debug_name(relative_pdf_path) if debug_ocr else None

    for page in pages:
        if not should_run_ocr(page, ocr_mode):
            continue

        page.ocr_attempted = True
        page_debug_dir = debug_root / f"page_{page.index:04d}" if debug_root else None
        ocr_result = ocr_engine.ocr_page(
            pdf_path=pdf_path,
            page_index=page.index - 1,
            lang=ocr_lang,
            dpi=ocr_dpi,
            psm_values=ocr_psm_values,
            debug_dir=page_debug_dir,
        )

        if ocr_mode == "force":
            if ocr_result.score > 0:
                page.text = ocr_result.text
                page.method = ocr_result.method
                page.score = ocr_result.score
                page.ocr_used = True
                used_ocr = True
        elif ocr_result.score > page.score:
            page.text = ocr_result.text
            page.method = ocr_result.method
            page.score = ocr_result.score
            page.ocr_used = True
            used_ocr = True

        page.kind = classify_page(page.score, PageProbe(page.image_count, page.largest_image_ratio))

    return pages, used_ocr


def build_markdown(
    pdf_path: Path,
    relative_pdf_path: Path,
    pages: list[PageInsight],
    extractor_names: list[str],
    ocr_engine: OCREngine | None,
    ocr_mode: str,
    ocr_used: bool,
    quality: dict[str, object],
) -> tuple[str, bool]:
    title = pdf_path.stem
    inferred_profile = infer_document_profile(relative_pdf_path, title)
    converted_at = datetime.now().astimezone().isoformat(timespec="seconds")
    page_count = len(pages)
    needs_ocr = not has_extractable_text(page.text for page in pages)
    document_status = str(quality["status"])
    usable_pages = list(quality["usable_pages"])
    missing_pages = list(quality["missing_pages"])
    usable_ratio = float(quality["usable_ratio"])

    page_methods = [
        {
            "page": page.index,
            "kind": page.kind,
            "method": page.method,
            "score": page.score,
            "image_count": page.image_count,
            "largest_image_ratio": round(page.largest_image_ratio, 3),
            "ocr_attempted": page.ocr_attempted,
            "ocr_used": page.ocr_used,
        }
        for page in pages
    ]

    front_matter = {
        "title": title,
        "source_pdf": str(pdf_path.resolve()),
        "source_relative_path": relative_pdf_path.as_posix(),
        "converted_at": converted_at,
        "page_count": page_count,
        "converter": SCRIPT_NAME,
        "extractors_available": extractor_names,
        "ocr_mode": ocr_mode,
        "ocr_engine": ocr_engine.name if ocr_engine else "",
        "ocr_used": ocr_used,
        "ocr_required": needs_ocr,
        "document_status": document_status,
        "body_source": "extracted_text" if document_status == "clean" else "metadata_inferred_plus_extracted_text",
        "inferred_group": inferred_profile["group_name"],
        "inferred_topic": inferred_profile["topic_name"],
        "inferred_document_type": inferred_profile["document_type"],
        "inferred_years": inferred_profile["years"],
        "inferred_school_years": inferred_profile["school_years"],
        "inferred_keywords": inferred_profile["keywords"],
        "usable_text_pages": usable_pages,
        "missing_text_pages": missing_pages,
        "usable_text_ratio": round(usable_ratio, 3),
        "page_methods": page_methods,
    }

    lines = ["---"]
    lines.extend(f"{key}: {yaml_value(value)}" for key, value in front_matter.items())
    lines.extend(["---", "", f"# {title}", ""])
    lines.append(f"> Source PDF: `{relative_pdf_path.as_posix()}`")
    lines.append(f"> Extractors available: `{', '.join(extractor_names)}`")
    lines.append(f"> OCR mode: `{ocr_mode}`")
    lines.append(f"> Document status: `{document_status}`")
    if ocr_engine:
        lines.append(f"> OCR engine: `{ocr_engine.name}`")
    if needs_ocr:
        lines.append("> OCR required: this file still needs OCR support or stronger OCR output.")
    lines.append("")

    if document_status != "clean":
        lines.append("## Document Profile")
        lines.append("")
        lines.append(f"- Group: {inferred_profile['group_name']}")
        lines.append(f"- Topic: {inferred_profile['topic_name']}")
        lines.append(f"- Document type: {inferred_profile['document_type']}")
        if inferred_profile["years"]:
            lines.append(f"- Years detected: {', '.join(inferred_profile['years'])}")
        if inferred_profile["school_years"]:
            lines.append(f"- School years detected: {', '.join(inferred_profile['school_years'])}")
        lines.append("")

        lines.append("## Inferred Summary")
        lines.append("")
        lines.append(str(inferred_profile["summary"]))
        lines.append("")

        lines.append("## Search Keywords")
        lines.append("")
        for keyword in inferred_profile["keywords"]:
            lines.append(f"- {keyword}")
        lines.append("")

        lines.append("## Suggested Questions")
        lines.append("")
        for question in inferred_profile["suggested_questions"]:
            lines.append(f"- {question}")
        lines.append("")

        lines.append("## Extraction Status")
        lines.append("")
        lines.append(f"- Total pages: {page_count}")
        lines.append(f"- Usable text pages: {len(usable_pages)}/{page_count}")
        if missing_pages:
            missing_label = ", ".join(str(page_number) for page_number in missing_pages)
            lines.append(f"- Pages still missing text: {missing_label}")
        if document_status == "ocr_pending":
            lines.append("- Current result is metadata-only. This file should not be treated as clean text data yet.")
        elif document_status == "partial":
            lines.append("- Partial extraction only. Review pending pages before using this as final clean data.")
        lines.append("")

    text_pages = [page for page in pages if page.text.strip()]
    for page in text_pages:
        lines.append(f"## Page {page.index}")
        lines.append("")
        lines.append(f"<!-- page_kind: {page.kind} -->")
        lines.append(f"<!-- extracted_by: {page.method} -->")
        lines.append("")
        lines.append(page.text)
        lines.append("")

    if missing_pages:
        lines.append("## Missing Pages")
        lines.append("")
        for page in pages:
            if page.index not in missing_pages:
                continue
            lines.append(
                f"- Page {page.index}: kind={page.kind}, method={page.method}, score={page.score}, images={page.image_count}"
            )
        lines.append("")

    markdown = "\n".join(lines).rstrip() + "\n"
    return markdown, needs_ocr


def convert_pdf(
    pdf_path: Path,
    input_dir: Path,
    output_dir: Path,
    extractors: list[Extractor],
    ocr_engine: OCREngine | None,
    force: bool,
    verbose: bool,
    ocr_mode: str,
    ocr_lang: str,
    ocr_dpi: int,
    ocr_psm_values: list[int],
    debug_ocr: bool,
    incomplete_policy: str,
    pending_dir_name: str,
) -> tuple[str, str]:
    relative_pdf_path = pdf_path.relative_to(input_dir)
    main_output_path = output_dir / relative_pdf_path.with_suffix(".md")
    pending_output_path = output_dir / pending_dir_name / relative_pdf_path.with_suffix(".md")

    documents = extract_documents(pdf_path, extractors)
    if not documents:
        raise RuntimeError(
            "Could not extract this PDF. Install one of: pymupdf, pdfplumber, pypdf, PyPDF2"
        )

    page_count = max(document.page_count for document in documents)
    probes = probe_pdf_pages(pdf_path)
    while len(probes) < page_count:
        probes.append(PageProbe())

    pages: list[PageInsight] = []
    for page_index in range(page_count):
        candidates: list[tuple[str, str]] = []
        source_methods: list[str] = []
        for document in documents:
            raw_text = document.pages[page_index] if page_index < len(document.pages) else ""
            candidates.append((document.method, raw_text))
            source_methods.append(document.method)

        best_text, best_method, best_score = choose_best_page_text(candidates)
        probe = probes[page_index]
        pages.append(
            PageInsight(
                index=page_index + 1,
                text=best_text,
                method=best_method,
                score=best_score,
                image_count=probe.image_count,
                largest_image_ratio=probe.largest_image_ratio,
                kind=classify_page(best_score, probe),
                source_methods=source_methods,
            )
        )

    pages, ocr_used = apply_ocr_to_pages(
        pdf_path=pdf_path,
        relative_pdf_path=relative_pdf_path,
        pages=pages,
        ocr_engine=ocr_engine,
        ocr_mode=ocr_mode,
        ocr_lang=ocr_lang,
        ocr_dpi=ocr_dpi,
        ocr_psm_values=ocr_psm_values,
        debug_ocr=debug_ocr,
        output_dir=output_dir,
    )

    quality = assess_document_quality(pages)
    document_status = str(quality["status"])
    output_path, routed_pending = resolve_output_path(
        relative_pdf_path=relative_pdf_path,
        output_dir=output_dir,
        pending_dir_name=pending_dir_name,
        incomplete_policy=incomplete_policy,
        document_status=document_status,
    )

    if output_path is None:
        return "skipped", f"Skip incomplete: {relative_pdf_path.as_posix()} ({document_status})"

    if output_path.exists() and not force:
        return "skipped", f"Skip existing: {output_path}"

    alternate_path = pending_output_path if output_path == main_output_path else main_output_path
    if force and alternate_path.exists():
        alternate_path.unlink()

    markdown, needs_ocr = build_markdown(
        pdf_path=pdf_path,
        relative_pdf_path=relative_pdf_path,
        pages=pages,
        extractor_names=[document.method for document in documents],
        ocr_engine=ocr_engine,
        ocr_mode=ocr_mode,
        ocr_used=ocr_used,
        quality=quality,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    if routed_pending:
        return "pending", f"Pending OCR: {output_path}"
    if needs_ocr:
        return "ocr_required", f"OCR required: {output_path}"
    if verbose:
        return "converted", f"Converted: {output_path}"
    return "converted", output_path.name


def main() -> int:
    args = parse_args()
    project_root = Path.cwd().resolve()
    input_dir, input_error, input_dir_auto_selected = resolve_input_dir(args.input, project_root)
    output_dir = Path(args.output).resolve()
    ocr_psm_values = parse_ocr_psm(args.ocr_psm)

    if input_error:
        safe_print(input_error, error=True)
        return 1
    assert input_dir is not None

    if input_dir_auto_selected:
        safe_print(f"Using detected input directory: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    extractors = discover_extractors()
    if not extractors:
        safe_print(
            "No supported PDF extractor was found.\n"
            "Install one of these packages first:\n"
            "  pip install pymupdf\n"
            "  pip install pdfplumber\n"
            "  pip install pypdf\n"
            "Optional compatibility fallback:\n"
            "  pip install PyPDF2",
            error=True,
        )
        return 2

    ocr_engine = discover_ocr_engine()
    if args.ocr == "force" and ocr_engine is None:
        safe_print(
            "OCR mode is 'force' but OCR tools are not available.\n"
            "Missing requirement: tesseract executable on PATH and Python packages pytesseract + pymupdf.\n"
            "Suggested install:\n"
            "  pip install pytesseract pymupdf pillow\n"
            "  Then install Tesseract OCR for Windows and add tesseract.exe to PATH.",
            error=True,
        )
        return 2

    pdf_files, non_pdf_count = scan_input_files(input_dir)
    if args.limit is not None:
        pdf_files = pdf_files[: max(args.limit, 0)]

    summary = Summary(total_pdfs=len(pdf_files), non_pdf_skipped=non_pdf_count)

    if args.verbose:
        safe_print(f"Extractors: {', '.join(extractor.name for extractor in extractors)}")
        safe_print(f"OCR engine: {ocr_engine.name if ocr_engine else 'not available'}")
        safe_print(f"OCR PSM values: {ocr_psm_values}")
        safe_print(f"Incomplete policy: {args.incomplete_policy}")
        safe_print(f"Input: {input_dir}")
        safe_print(f"Output: {output_dir}")
        safe_print(f"PDF files found: {summary.total_pdfs}")
        safe_print(f"Non-PDF files skipped while scanning: {summary.non_pdf_skipped}")

    for index, pdf_path in enumerate(pdf_files, start=1):
        try:
            status, message = convert_pdf(
                pdf_path=pdf_path,
                input_dir=input_dir,
                output_dir=output_dir,
                extractors=extractors,
                ocr_engine=ocr_engine,
                force=args.force,
                verbose=args.verbose,
                ocr_mode=args.ocr,
                ocr_lang=args.ocr_lang,
                ocr_dpi=args.ocr_dpi,
                ocr_psm_values=ocr_psm_values,
                debug_ocr=args.debug_ocr,
                incomplete_policy=args.incomplete_policy,
                pending_dir_name=args.pending_dir_name,
            )
            if status == "converted":
                summary.converted += 1
            elif status == "pending":
                summary.pending_ocr += 1
                summary.needs_ocr += 1
            elif status == "skipped":
                summary.skipped_existing += 1
            elif status == "ocr_required":
                summary.converted += 1
                summary.needs_ocr += 1

            if args.verbose:
                safe_print(message)
            elif index % 25 == 0 or index == summary.total_pdfs:
                safe_print(f"Processed {index}/{summary.total_pdfs}")
        except Exception as error:
            summary.errors += 1
            safe_print(f"Error: {pdf_path} -> {error}", error=True)

    safe_print("")
    safe_print("Summary")
    safe_print(f"- Total PDF files found: {summary.total_pdfs}")
    safe_print(f"- Clean documents written: {summary.converted}")
    safe_print(f"- Routed to pending OCR: {summary.pending_ocr}")
    safe_print(f"- Skipped existing: {summary.skipped_existing}")
    safe_print(f"- Needs OCR: {summary.needs_ocr}")
    safe_print(f"- Errors: {summary.errors}")
    safe_print(f"- Non-PDF files skipped: {summary.non_pdf_skipped}")

    return 0 if summary.errors == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
