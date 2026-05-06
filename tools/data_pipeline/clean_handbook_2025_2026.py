from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


DEFAULT_INPUT = Path(
    "data/qa_generated_fixed/Sổ tay sinh viên các năm/6. Sổ tay sinh viên các năm/8. SO TAY SINH VIEN 2025-2026.md"
)


def _replace_first(
    text: str,
    pattern: str,
    replacement: str,
    label: str,
    changes: list[str],
    *,
    flags: int = re.MULTILINE | re.DOTALL,
) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count:
        changes.append(label)
    return updated


def _replace_all(
    text: str,
    pattern: str,
    replacement: str,
    label: str,
    changes: list[str],
    *,
    flags: int = re.MULTILINE,
) -> str:
    updated, count = re.subn(pattern, replacement, text, flags=flags)
    if count:
        changes.append(f"{label} x{count}")
    return updated


def clean_handbook_text(text: str) -> tuple[str, list[str]]:
    changes: list[str] = []
    original = text

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    prompt_artifact_patterns = [
        r"(?m)^(?:Tuyệt vời!\s*)?Dưới đây là văn bản[^\n]*\n(?:\n)?",
        r"(?m)^Here is the restored Markdown[^\n]*\n(?:\n)?",
    ]
    for index, pattern in enumerate(prompt_artifact_patterns, start=1):
        text = _replace_all(
            text,
            pattern,
            "",
            f"removed_prompt_artifact_{index}",
            changes,
        )

    literal_replacements = {
        'source_qa_file: "data/qa_generated_fixed/S tay sinh viên cc nm/6. S tay sinh viên cc nm/8. SO TAY SINH VIEN 2025-2026.md"': 'source_qa_file: "data/qa_generated_fixed/Sổ tay sinh viên các năm/6. Sổ tay sinh viên các năm/8. SO TAY SINH VIEN 2025-2026.md"',
        'source_clean_file: "clean_data/S tay sinh viên cc nm/6. S tay sinh viên cc nm/8. SO TAY SINH VIEN 2025-2026.md"': 'source_clean_file: "clean_data/Sổ tay sinh viên các năm/6. Sổ tay sinh viên các năm/8. SO TAY SINH VIEN 2025-2026.md"',
        'source_pdf: "S tay sinh viên cc nm/6. S tay sinh viên cc nm/8. SO TAY SINH VIEN 2025-2026.pdf"': 'source_pdf: "Sổ tay sinh viên các năm/6. Sổ tay sinh viên các năm/8. SO TAY SINH VIEN 2025-2026.pdf"',
        'questions_file: "data/qa_generated_fixed/S tay sinh viên cc nm/6. S tay sinh viên cc nm/8. SO TAY SINH VIEN 2025-2026.questions.md"': 'questions_file: "data/qa_generated_fixed/Sổ tay sinh viên các năm/6. Sổ tay sinh viên các năm/8. SO TAY SINH VIEN 2025-2026.questions.md"',
        "taichinh@i ctu.edu.vn": "taichinh@ictu.edu.vn",
        "http:// www.ictu.edu.vn": "http://www.ictu.edu.vn",
        "http:// www.ictu. edu.vn": "http://www.ictu.edu.vn",
        "Website: www.ictu.edu.vn##": "Website: www.ictu.edu.vn\n\n##",
        "Website: www.ictu.edu.vn## Chunk": "Website: www.ictu.edu.vn\n\n## Chunk",
        "PHN I > VII. Cơ cấu tổ chức bộ máy": "PHẦN I > VII. Cơ cấu tổ chức bộ máy",
        "PHN I > VI. Địa chỉ liên hệ": "PHẦN I > VI. Địa chỉ liên hệ",
        "PHN I > II. Tầm nhìn": "PHẦN I > II. Tầm nhìn",
        "Ngữ cảnh chunk: PHN I > VII. Cơ cấu tổ chức bộ máy": "Ngữ cảnh chunk: PHẦN I > VII. Cơ cấu tổ chức bộ máy",
        "Ngữ cảnh chunk: PHN I > VI. Địa chỉ liên hệ.": "Ngữ cảnh chunk: PHẦN I > VI. Địa chỉ liên hệ.",
        "Ngữ cảnh chunk: PHN I > II. Tầm nhìn.": "Ngữ cảnh chunk: PHẦN I > II. Tầm nhìn.",
    }
    for old, new in literal_replacements.items():
        if old in text:
            text = text.replace(old, new)
            changes.append(f"literal:{old[:40]}")

    text = _replace_first(
        text,
        (
            r"ĐẠI HỌC THÁI NGUYÊN TRƯỜNG ĐẠI HỌC CÔNG NGHỆ THÔNG TIN VÀ TRUYỀN THÔNG "
            r"-+ SỔ TAY SINH VIÊN Dành cho sinh viên khóa 24 http://www\.ictu\.edu\.vn "
            r"Lưu hành nội bộ Thái Nguyên - Năm 20 25"
        ),
        (
            "ĐẠI HỌC THÁI NGUYÊN\n"
            "TRƯỜNG ĐẠI HỌC CÔNG NGHỆ THÔNG TIN VÀ TRUYỀN THÔNG\n"
            "-----------------------\n"
            "SỔ TAY SINH VIÊN\n"
            "Dành cho sinh viên khóa 24\n"
            "http://www.ictu.edu.vn\n"
            "Lưu hành nội bộ\n"
            "Thái Nguyên - Năm 2025"
        ),
        "formatted_cover_block",
        changes,
    )

    chunk_002_003 = """## Chunk 002 - IV. Giá trị cốt lõi/Giá trị văn hóa

- `chunk_id`: `8_so_tay_sinh_vien_2025_2026__0002`
- `section_path`: `PHẦN I > Mục lục > IV. Giá trị cốt lõi/Giá trị văn hóa`
- `pages`: `2`

Tài liệu nguồn: 8. SO TAY SINH VIEN 2025-2026.
Ngữ cảnh chunk: PHẦN I > Mục lục > IV. Giá trị cốt lõi/Giá trị văn hóa.

TRUYỀN THÔNG - ĐẠI HỌC THÁI NGUYÊN .. ................................ ................................ ...........

- Giới thiệu về Trường ................................ ................................ ................................ .......... 4

II. Tầm nhìn ................................ ................................ ................................ ........................... 4

III. Sứ mạng ................................ ................................ ................................ ........................... 4

IV. Giá trị cốt lõi/Giá trị văn hóa ................................ ................................ .......................... 4

- Triết lý giáo dục ................................ ................................ ................................ ............................ 4

## Chunk 003 - VII. Cơ cấu tổ chức bộ máy

- `chunk_id`: `8_so_tay_sinh_vien_2025_2026__0003`
- `section_path`: `PHẦN I > Mục lục > VII. Cơ cấu tổ chức bộ máy`
- `pages`: `2`

Tài liệu nguồn: 8. SO TAY SINH VIEN 2025-2026.
Ngữ cảnh chunk: PHẦN I > Mục lục > VII. Cơ cấu tổ chức bộ máy.

VI. Địa chỉ liên hệ ................................ ................................ ................................ ................. 4

VII. Cơ cấu tổ chức bộ máy ................................ ................................ ................................ ......... 5

"""
    text = _replace_first(
        text,
        r"## Chunk 002 - .*?(?=## Chunk 004 - )",
        chunk_002_003,
        "reformatted_toc_chunks_002_003",
        changes,
    )

    chunk_009_010 = """## Chunk 009 - II. Tầm nhìn

- `chunk_id`: `8_so_tay_sinh_vien_2025_2026__0009`
- `section_path`: `PHẦN I > II. Tầm nhìn`
- `pages`: `4`

Tài liệu nguồn: 8. SO TAY SINH VIEN 2025-2026.
Ngữ cảnh chunk: PHẦN I > II. Tầm nhìn.

GIỚI THIỆU CHUNG VỀ TRƯỜNG ĐẠI HỌC CÔNG NGHỆ THÔNG TIN & TRUYỀN THÔNG - ĐẠI HỌC THÁI NGUYÊN

- Giới thiệu về Trường

Khoa Công nghệ Thông tin là đơn vị đào tạo thành viên thuộc Đại học Thái Nguyên được thành lập ngày 14 tháng 11 năm 2001 theo Quyết định số 6946/Q-BGDĐT-TCCB của Bộ trưởng Bộ Giáo dục và Đào tạo. Sau 10 năm xây dựng và phát triển, ngày 30 tháng 3 năm 2011, Thủ tướng Chính phủ ký Quyết định số 468/Q-TTg thành lập Trường Đại học Công nghệ Thông tin và Truyền thông trên cơ sở nâng cấp Khoa Công nghệ Thông tin thuộc Đại học Thái Nguyên.

II. Tầm nhìn
Trường Đại học Công nghệ Thông tin và Truyền thông trở thành Trường đại học ứng dụng, đa ngành, đa lĩnh vực, trên nền tảng số hàng đầu trong hệ thống giáo dục đại học Việt Nam.

## Chunk 010 - VI. Địa chỉ liên hệ

- `chunk_id`: `8_so_tay_sinh_vien_2025_2026__0010`
- `section_path`: `PHẦN I > VI. Địa chỉ liên hệ`
- `pages`: `4`

Tài liệu nguồn: 8. SO TAY SINH VIEN 2025-2026.
Ngữ cảnh chunk: PHẦN I > VI. Địa chỉ liên hệ.

III. Sứ mạng
Đào tạo nguồn nhân lực trình độ đại học, sau đại học; bồi dưỡng ngắn hạn; nghiên cứu khoa học và chuyển giao công nghệ đáp ứng nhu cầu của thị trường lao động và phù hợp với Chiến lược Quốc gia về cách mạng công nghiệp lần thứ tư và Chương trình Chuyển đổi số Quốc gia, phục vụ phát triển kinh tế - văn hóa - xã hội của đất nước.

IV. Giá trị cốt lõi/Giá trị văn hóa
Đoàn kết - Tận tâm - Sáng tạo - Thực tiễn.

- Triết lý giáo dục

Giáo dục toàn diện lấy người học làm trung tâm; đào tạo hình mẫu công dân số; kiến tạo tương lai, nuôi dưỡng lòng nhân ái.

VI. Địa chỉ liên hệ
Trường Đại học Công nghệ Thông tin & Truyền thông - Đại học Thái Nguyên
(University of Information and Communication Technology, Thai Nguyen University)
Phường Quyết Thắng, tỉnh Thái Nguyên
Điện thoại: 0208.3846254 Fax: 0208.3846237
E-mail: contact@ictu.edu.vn
Website: www.ictu.edu.vn

"""
    text = _replace_first(
        text,
        r"## Chunk 009 - .*?(?=## Chunk 011 - )",
        chunk_009_010,
        "reformatted_intro_chunks_009_010",
        changes,
    )

    text = _replace_all(
        text,
        r"(?m)^(Website: [^\n]+)\n(## Chunk \d+ - )",
        r"\1\n\n\2",
        "separated_chunk_after_website",
        changes,
    )

    text = _replace_all(
        text,
        r"\n{3,}",
        "\n\n",
        "collapsed_extra_blank_lines",
        changes,
    )

    if text != original and not text.endswith("\n"):
        text += "\n"
        changes.append("added_trailing_newline")

    return text, changes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Clean formatting for the 2025-2026 student handbook markdown without deleting document content."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Input markdown file. Defaults to the 2025-2026 RAG context file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the cleaned result to a new file instead of modifying the input file.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the cleaned content back to --input.",
    )
    return parser.parse_args()


def main() -> int:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    args = parse_args()
    input_path: Path = args.input

    if args.apply and args.output:
        raise SystemExit("Use either --apply or --output, not both.")
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    original = input_path.read_text(encoding="utf-8")
    cleaned, changes = clean_handbook_text(original)

    if not changes:
        print("No changes needed.")
        return 0

    print(f"Detected {len(changes)} cleaning actions.")
    for item in changes:
        print(f"- {item}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(cleaned, encoding="utf-8")
        print(f"Wrote cleaned file to: {args.output}")
        return 0

    if args.apply:
        input_path.write_text(cleaned, encoding="utf-8")
        print(f"Updated file in place: {input_path}")
        return 0

    print("Dry run only. Re-run with --apply or --output to write the cleaned file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
