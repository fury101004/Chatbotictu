from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "main.py").exists() and (parent / "services").is_dir():
            return parent
    return Path(__file__).resolve().parents[2]


ROOT = _find_repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.rag_tools import detect_tool_from_path  # noqa: E402
from config.settings import settings  # noqa: E402

SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt"}
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
TITLE_PATTERN = re.compile(r'^title:\s*"?(.+?)"?\s*$', re.MULTILINE)
HEADING_PATTERN = re.compile(r"^#\s+(.+)$", re.MULTILINE)
QUESTION_PATTERN = re.compile(r"^\*\*Q:\*\*", re.MULTILINE)


def _iter_corpus_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )


def _split_frontmatter(text: str) -> tuple[str, str]:
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return "", text
    return match.group(1), text[match.end() :]


def _extract_title(frontmatter: str, body: str, path: Path) -> str:
    title_match = TITLE_PATTERN.search(frontmatter)
    if title_match:
        return title_match.group(1).strip()

    heading_match = HEADING_PATTERN.search(body)
    if heading_match:
        return heading_match.group(1).strip()

    return path.stem


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _build_numeric_summary(values: list[int]) -> dict[str, float | int]:
    return {
        "avg": round(statistics.fmean(values), 2) if values else 0,
        "min": min(values) if values else 0,
        "max": max(values) if values else 0,
    }


def analyze_corpus(corpus_root: Path) -> dict:
    files = _iter_corpus_files(corpus_root)
    samples: list[dict] = []
    tool_distribution: Counter[str] = Counter()
    folder_distribution: Counter[str] = Counter()

    title_char_values: list[int] = []
    title_word_values: list[int] = []
    content_char_values: list[int] = []
    content_word_values: list[int] = []
    qa_pair_values: list[int] = []

    for path in files:
        raw_text = path.read_text(encoding="utf-8", errors="ignore")
        frontmatter, body = _split_frontmatter(raw_text)
        title = _extract_title(frontmatter, body, path)
        relative_path = path.relative_to(corpus_root)
        top_folder = relative_path.parts[0] if len(relative_path.parts) > 1 else "(root)"
        tool_name = detect_tool_from_path(path) or "unassigned"
        qa_pairs = len(QUESTION_PATTERN.findall(body))

        sample = {
            "path": relative_path.as_posix(),
            "tool_name": tool_name,
            "top_folder": top_folder,
            "title": title,
            "title_chars": len(title),
            "title_words": _word_count(title),
            "content_chars": len(body),
            "content_words": _word_count(body),
            "qa_pairs": qa_pairs,
        }
        samples.append(sample)

        tool_distribution[tool_name] += 1
        folder_distribution[top_folder] += 1
        title_char_values.append(sample["title_chars"])
        title_word_values.append(sample["title_words"])
        content_char_values.append(sample["content_chars"])
        content_word_values.append(sample["content_words"])
        qa_pair_values.append(qa_pairs)

    longest_content = max(samples, key=lambda item: item["content_chars"], default=None)
    shortest_content = min(samples, key=lambda item: item["content_chars"], default=None)
    longest_title = max(samples, key=lambda item: item["title_chars"], default=None)
    shortest_title = min(samples, key=lambda item: item["title_chars"], default=None)

    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "corpus_root": str(corpus_root),
        "total_samples": len(samples),
        "total_qa_pairs": sum(qa_pair_values),
        "tool_distribution": dict(sorted(tool_distribution.items())),
        "folder_distribution": dict(sorted(folder_distribution.items())),
        "title_stats": {
            "chars": _build_numeric_summary(title_char_values),
            "words": _build_numeric_summary(title_word_values),
            "shortest_sample": shortest_title,
            "longest_sample": longest_title,
        },
        "content_stats": {
            "chars": _build_numeric_summary(content_char_values),
            "words": _build_numeric_summary(content_word_values),
            "shortest_sample": shortest_content,
            "longest_sample": longest_content,
        },
        "qa_pair_stats": _build_numeric_summary(qa_pair_values),
        "samples": samples,
    }


def build_markdown_summary(report: dict) -> str:
    lines = [
        "# Tóm tắt phân tích dữ liệu",
        "",
        f"- Tổng số mẫu: {report['total_samples']}",
        f"- Tổng số cặp Q/A: {report['total_qa_pairs']}",
        "",
        "## Độ dài title",
        f"- Số ký tự trung bình: {report['title_stats']['chars']['avg']}",
        f"- Số ký tự min/max: {report['title_stats']['chars']['min']} / {report['title_stats']['chars']['max']}",
        f"- Số từ trung bình: {report['title_stats']['words']['avg']}",
        f"- Số từ min/max: {report['title_stats']['words']['min']} / {report['title_stats']['words']['max']}",
        "",
        "## Độ dài content",
        f"- Số ký tự trung bình: {report['content_stats']['chars']['avg']}",
        f"- Số ký tự min/max: {report['content_stats']['chars']['min']} / {report['content_stats']['chars']['max']}",
        f"- Số từ trung bình: {report['content_stats']['words']['avg']}",
        f"- Số từ min/max: {report['content_stats']['words']['min']} / {report['content_stats']['words']['max']}",
        "",
        "## Phân bố theo nhóm tri thức",
    ]

    for tool_name, count in report["tool_distribution"].items():
        lines.append(f"- {tool_name}: {count} mẫu")

    lines.extend(
        [
            "",
            "## 5 file dài nhất theo content",
        ]
    )
    longest_samples = sorted(
        report["samples"],
        key=lambda item: item["content_chars"],
        reverse=True,
    )[:5]
    for item in longest_samples:
        lines.append(
            f"- {item['path']} | {item['content_chars']} ký tự | {item['qa_pairs']} cặp Q/A"
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Phân tích dữ liệu corpus chatbot.")
    parser.add_argument(
        "--corpus-root",
        default=str(settings.QA_CORPUS_ROOT),
        help="Thư mục chứa corpus cần phân tích.",
    )
    parser.add_argument(
        "--output-json",
        default=str(ROOT / "reports" / "generated" / "dataset_analysis.json"),
        help="Đường dẫn file JSON đầu ra.",
    )
    parser.add_argument(
        "--output-md",
        default=str(ROOT / "reports" / "generated" / "dataset_analysis.md"),
        help="Đường dẫn file Markdown đầu ra.",
    )
    args = parser.parse_args()

    corpus_root = Path(args.corpus_root)
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)

    report = analyze_corpus(corpus_root)
    output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    output_md.write_text(build_markdown_summary(report), encoding="utf-8")

    print(json.dumps({
        "status": "ok",
        "total_samples": report["total_samples"],
        "total_qa_pairs": report["total_qa_pairs"],
        "output_json": str(output_json),
        "output_md": str(output_md),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
