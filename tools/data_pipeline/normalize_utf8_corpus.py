from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".html", ".js", ".css", ".json", ".yml", ".yaml", ".py"}
DEFAULT_TARGETS = [
    "data/primary_corpus",
    "data/systemprompt.md",
    "data/bot-rule.md",
    "services/rag_prompts.py",
    "views/frontend/templates",
    "views/frontend/assets",
]
MOJIBAKE_PATTERNS = [
    re.compile(r"Ã[\x80-\xBFÀ-ÿ]"),
    re.compile(r"áº."),
    re.compile(r"á»."),
    re.compile(r"â€."),
    re.compile(r"â†."),
    re.compile(r"Ä[‘ƒ]"),
    re.compile(r"ư"),
    re.compile(r"ðŸ"),
]
VIETNAMESE_CHARS = (
    "ăâđêôơưĂÂĐÊÔƠƯ"
    "áàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
    "ÁÀẢÃẠẮẰẲẴẶẤẦẨẪẬÉÈẺẼẸẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴ"
)


def _iter_text_files(path: Path):
    if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
        yield path
        return

    if path.is_dir():
        for candidate in path.rglob("*"):
            if candidate.is_file() and candidate.suffix.lower() in TEXT_SUFFIXES:
                yield candidate


def _decode_bytes(raw: bytes) -> str:
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _roundtrip_variant(text: str, source_encoding: str) -> str | None:
    try:
        return text.encode(source_encoding).decode("utf-8")
    except UnicodeError:
        return None


def _repair_variants(text: str) -> list[str]:
    variants = [text]
    frontier = [text]

    for _ in range(2):
        next_frontier: list[str] = []
        for current in frontier:
            for source_encoding in ("cp1252", "latin-1", "cp1258"):
                candidate = _roundtrip_variant(current, source_encoding)
                if not candidate or candidate in variants:
                    continue
                variants.append(candidate)
                next_frontier.append(candidate)
        if not next_frontier:
            break
        frontier = next_frontier

    return variants


def _mojibake_marker_count(text: str) -> int:
    return sum(len(pattern.findall(text)) for pattern in MOJIBAKE_PATTERNS)


def _score_text(text: str) -> tuple[int, int]:
    marker_count = _mojibake_marker_count(text)
    vietnamese_count = sum(1 for ch in text if ch in VIETNAMESE_CHARS)
    c1_control_count = sum(1 for ch in text if 0x80 <= ord(ch) <= 0x9F)
    return marker_count + c1_control_count, -vietnamese_count


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    return normalized


def normalize_file(path: Path, *, dry_run: bool) -> dict[str, object]:
    raw = path.read_bytes()
    decoded = _decode_bytes(raw)
    best = _normalize_text(decoded)
    best_score = _score_text(best)

    for variant in _repair_variants(decoded):
        candidate = _normalize_text(variant)
        score = _score_text(candidate)
        if score < best_score:
            best = candidate
            best_score = score

    try:
        current = raw.decode("utf-8")
    except UnicodeDecodeError:
        current = decoded
    current_normalized = _normalize_text(current)
    changed = best != current_normalized

    result = {
        "path": str(path),
        "changed": changed,
        "marker_score_before": _score_text(current_normalized)[0],
        "marker_score_after": best_score[0],
    }

    if changed and not dry_run:
        path.write_text(best, encoding="utf-8", newline="\n")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize corpus/prompt/template files to UTF-8 NFC and repair common mojibake.")
    parser.add_argument("--target", action="append", default=[], help="Target file/folder (can repeat).")
    parser.add_argument("--include-clean-data", action="store_true", help="Include clean_data directory.")
    parser.add_argument("--dry-run", action="store_true", help="Only report files that would change.")
    parser.add_argument("--report", default="reports/utf8_normalization_report.json", help="Path to JSON report.")
    args = parser.parse_args()

    targets = [Path(item) for item in (args.target or DEFAULT_TARGETS)]
    if not args.target:
        targets = [Path(item) for item in DEFAULT_TARGETS]
    if args.include_clean_data:
        targets.append(Path("clean_data"))

    files: list[Path] = []
    seen: set[Path] = set()
    for target in targets:
        if not target.exists():
            continue
        for file_path in _iter_text_files(target):
            resolved = file_path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(file_path)

    results = [normalize_file(path, dry_run=args.dry_run) for path in files]
    changed = [item for item in results if item["changed"]]

    report = {
        "total_files": len(results),
        "changed_files": len(changed),
        "dry_run": args.dry_run,
        "targets": [str(t) for t in targets],
        "changes": changed,
    }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Scanned {len(results)} files")
    print(f"Changed {len(changed)} files")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
