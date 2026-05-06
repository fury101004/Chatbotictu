# rebuild_data_from_original_pdf.py
# Mục đích:
# - Không sửa file .md bị lỗi font cũ nữa.
# - Đọc lại trực tiếp từ PDF gốc bằng PyMuPDF.
# - Xuất lại file .md sạch vào clean_data/
# - Đồng thời tạo file chunks JSONL cho RAG trong data/

import re
import json
import unicodedata
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    raise SystemExit(
        "Thiếu thư viện PyMuPDF. Cài bằng lệnh:\n"
        "pip install pymupdf tqdm"
    )

try:
    from tqdm import tqdm
except ImportError:
    tqdm = lambda x, **kwargs: x


# =========================
# CẤU HÌNH ĐƯỜNG DẪN
# =========================
PDF_DIR = Path("datapdf")        # thư mục chứa PDF gốc, có thể đổi thành data/raw_pdf nếu bạn dùng tên đó
CLEAN_DIR = Path("clean_data")   # nơi lưu .md sạch
DATA_DIR = Path("data")          # nơi lưu dữ liệu đưa vào RAG

CHUNK_FILE = DATA_DIR / "chunks.jsonl"

MIN_CHUNK_WORDS = 80
MAX_CHUNK_WORDS = 450


# =========================
# HÀM LÀM SẠCH
# =========================
BAD_CHARS = [
    "￾", "", "", "", "\x00", "\x0c",
    "�"
]

SKIP_LINE_PATTERNS = [
    r"^\s*\d+\s*$",
    r"^\s*MỤC LỤC\s*$",
    r"^\s*MC LC\s*$",
    r"^\s*Nội dung\s+Trang\s*$",
    r"^\s*Noi dung\s+Trang\s*$",
    r"^[-–—_=]{3,}$",
    r"^\.*$",
    r"^<!--.*-->$",
    r"^\s*extracted_by\s*:",
    r"^\s*page_kind\s*:",
]


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)

    for ch in BAD_CHARS:
        text = text.replace(ch, " ")

    # sửa khoảng trắng lỗi
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def is_bad_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return True

    for p in SKIP_LINE_PATTERNS:
        if re.search(p, s, flags=re.IGNORECASE):
            return True

    # bỏ dòng trang dạng "## Page 1" nếu có
    if re.match(r"^#{1,3}\s*Page\s+\d+", s, flags=re.IGNORECASE):
        return True

    return False


def is_probably_toc_page(text: str) -> bool:
    upper = text.upper()
    dot_count = text.count("...")
    has_toc = "MỤC LỤC" in upper or "MC LC" in upper
    has_page_col = "TRANG" in upper
    return has_toc or (has_page_col and dot_count >= 5)


def is_cover_page(text: str, page_index: int) -> bool:
    if page_index > 1:
        return False
    upper = text.upper()
    return (
        "SỔ TAY SINH VIÊN" in upper
        or "SO TAY SINH VIEN" in upper
        or "ĐẠI HỌC THÁI NGUYÊN" in upper
        or "DAI HOC THAI NGUYEN" in upper
    )


def convert_heading(line: str) -> str:
    s = line.strip()
    upper = s.upper()

    # Nếu PDF mất dấu ở tiêu đề, vẫn nhận dạng được
    if re.match(r"^(PHẦN|PHAN)\s+[IVXLCDM]+", upper):
        return "# " + s

    if re.match(r"^(CHƯƠNG|CHUONG|CHNG)\s+[IVXLCDM]+", upper):
        return "## " + s

    if re.match(r"^(ĐIỀU|DIEU|IU)\s+\d+", upper):
        return "### " + s

    if re.match(r"^[IVXLCDM]+\.\s+", s):
        return "### " + s

    if re.match(r"^[A-ZĐ]\.\s+", s):
        return "### " + s

    return s


def merge_broken_lines(lines):
    merged = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if not merged:
            merged.append(line)
            continue

        prev = merged[-1]

        line_is_heading = line.startswith("#")
        line_is_list = re.match(r"^[-+*]\s+", line)
        line_is_numbered = re.match(r"^\d+[\.\)]\s+", line)
        line_is_alpha = re.match(r"^[a-zA-ZĐ]\.\s+", line)
        prev_end_ok = prev.endswith((".", ":", ";", "!", "?", ")", "]"))

        if line_is_heading or line_is_list or line_is_numbered or line_is_alpha or prev_end_ok:
            merged.append(line)
        else:
            merged[-1] = prev + " " + line

    return merged


def slugify(filename: str) -> str:
    name = filename.lower()
    name = unicodedata.normalize("NFD", name)
    name = "".join(ch for ch in name if unicodedata.category(ch) != "Mn")
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"[\s-]+", "_", name)
    return name.strip("_")


# =========================
# PDF -> MD SẠCH
# =========================
def extract_pdf_to_clean_md(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    output_lines = []
    started = False

    for page_index in range(len(doc)):
        page = doc[page_index]
        text = page.get_text("text")
        text = normalize_text(text)

        if not text:
            continue

        # bỏ bìa và mục lục các trang đầu
        if page_index <= 5 and (is_cover_page(text, page_index) or is_probably_toc_page(text)):
            continue

        lines = []
        for raw_line in text.splitlines():
            line = normalize_text(raw_line)
            if is_bad_line(line):
                continue

            # bỏ footer/link nhiễu
            if re.search(r"www\.ictu\.edu\.vn|http://|https://|Lưu hành nội bộ|Thai Nguyen|Thái Nguyên", line, re.I):
                continue

            lines.append(line)

        for line in lines:
            upper = line.upper()

            # chỉ bắt đầu lấy từ nội dung chính
            if not started:
                if (
                    upper.startswith("PHẦN I")
                    or upper.startswith("PHAN I")
                    or "GIỚI THIỆU CHUNG" in upper
                    or "GII THIU CHUNG" in upper
                ):
                    started = True
                else:
                    continue

            output_lines.append(convert_heading(line))

    output_lines = merge_broken_lines(output_lines)

    md = []
    md.append("---")
    md.append(f'title: "{pdf_path.stem}"')
    md.append(f'source_pdf: "{pdf_path.as_posix()}"')
    md.append('converter: "rebuild_data_from_original_pdf.py"')
    md.append("---")
    md.append("")
    md.extend(output_lines)

    return "\n\n".join(md).strip() + "\n"


# =========================
# MD -> CHUNKS RAG
# =========================
def count_words(text: str) -> int:
    return len(text.split())


def split_sections(md_text: str):
    parts = re.split(r"(?=^#{1,3}\s+)", md_text, flags=re.MULTILINE)
    return [p.strip() for p in parts if p.strip()]


def get_title(section: str) -> str:
    for line in section.splitlines():
        if line.startswith("#"):
            return line.replace("#", "").strip()
    return "Nội dung"


def split_long_section(section: str):
    words = section.split()
    chunks = []

    for i in range(0, len(words), MAX_CHUNK_WORDS):
        part = " ".join(words[i:i + MAX_CHUNK_WORDS]).strip()
        if count_words(part) >= MIN_CHUNK_WORDS:
            chunks.append(part)

    return chunks


def build_chunks_from_md_files(md_files):
    chunks = []
    seen = set()

    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8", errors="ignore")
        sections = split_sections(text)

        for section in sections:
            title = get_title(section)

            if count_words(section) > MAX_CHUNK_WORDS:
                parts = split_long_section(section)
            else:
                parts = [section]

            for part in parts:
                part = part.strip()
                if count_words(part) < MIN_CHUNK_WORDS:
                    continue

                # chống trùng lặp đơn giản
                key = re.sub(r"\s+", " ", part.lower())[:1200]
                if key in seen:
                    continue
                seen.add(key)

                chunks.append({
                    "id": f"chunk_{len(chunks) + 1}",
                    "title": title,
                    "content": part,
                    "source": md_file.name
                })

    return chunks


# =========================
# MAIN
# =========================
def main():
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(PDF_DIR.rglob("*.pdf"))

    if not pdf_files:
        print(f"Không tìm thấy PDF gốc trong thư mục: {PDF_DIR.resolve()}")
        print("Bạn hãy sửa biến PDF_DIR ở đầu file cho đúng thư mục PDF gốc.")
        return

    clean_md_files = []

    print("Bước 1: Đọc lại PDF gốc và tạo clean_data/*.md")
    for pdf in tqdm(pdf_files):
        try:
            md = extract_pdf_to_clean_md(pdf)
            out_name = slugify(pdf.stem) + ".md"
            out_path = CLEAN_DIR / out_name
            out_path.write_text(md, encoding="utf-8")
            clean_md_files.append(out_path)
            print(f"OK: {pdf.name} -> {out_path}")
        except Exception as e:
            print(f"Lỗi file {pdf.name}: {e}")

    print("\nBước 2: Tạo data/chunks.jsonl cho RAG")
    chunks = build_chunks_from_md_files(clean_md_files)

    with CHUNK_FILE.open("w", encoding="utf-8") as f:
        for item in chunks:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"\nHoàn tất.")
    print(f"- Markdown sạch: {CLEAN_DIR.resolve()}")
    print(f"- File RAG: {CHUNK_FILE.resolve()}")
    print(f"- Tổng chunks: {len(chunks)}")


if __name__ == "__main__":
    main()
