from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


DEFAULT_ROOT = Path("data/primary_corpus/student_handbooks")


QUESTION_BLOCK_RE = re.compile(
    r"(?ms)^## Question (?P<number>\d+)\n\n"
    r"- `question_id`: `(?P<question_id>q\d+)`\n"
    r"- `source`: `(?P<source>[^`]+)`\n\n"
    r"\*\*Question:\*\* (?P<question>.+?)\n\n"
    r"\*\*Answer:\*\* (?P<answer>.+?)(?=\n## Question \d+\n|\Z)"
)


@dataclass
class QuestionEntry:
    source: str
    question: str
    answer: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Expand handbook .questions.md files with extra safe paraphrase questions.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="Directory that contains handbook .questions.md files.",
    )
    parser.add_argument(
        "--max-new-per-file",
        type=int,
        default=12,
        help="Maximum number of new questions appended to each file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing files.",
    )
    return parser.parse_args()


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    marker = "---\n"
    start = text.find(marker)
    if start > 0:
        text = text[start:]
    if not text.startswith(marker):
        return {}, text
    end = text.find("\n---\n", len(marker))
    if end == -1:
        return {}, text

    raw_meta = text[len(marker):end]
    body = text[end + len("\n---\n"):]
    meta: dict[str, str] = {}
    for line in raw_meta.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"')
    return meta, body.lstrip("\n")


def build_frontmatter(meta: dict[str, str]) -> str:
    ordered_keys = [
        "title",
        "source_context_file",
        "generated_at",
        "generator",
        "question_count",
    ]
    lines = ["---"]
    used = set()
    for key in ordered_keys:
        if key in meta:
            value = meta[key]
            if key == "question_count":
                lines.append(f"{key}: {value}")
            else:
                lines.append(f'{key}: "{value}"')
            used.add(key)
    for key in sorted(meta):
        if key in used:
            continue
        lines.append(f'{key}: "{meta[key]}"')
    lines.append("---")
    return "\n".join(lines)


def normalize_question(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text.strip()).casefold()
    return collapsed.rstrip(" ?!.")


def lower_first_for_clause(text: str) -> str:
    if not text:
        return text
    first_word = text.split(" ", 1)[0]
    if len(first_word) >= 2 and first_word.upper() == first_word:
        return text
    return text[:1].lower() + text[1:]


def replace_first_ci(text: str, pattern: str, replacement: str) -> str:
    return re.sub(pattern, replacement, text, count=1, flags=re.IGNORECASE)


def candidate_variants(question: str, source: str) -> list[str]:
    base = question.strip()
    if base.endswith("?"):
        base = base[:-1].strip()

    candidates: list[str] = []
    rewrite_rules = [
        (r"\bbao nhiêu\b", "mấy"),
        (r"\bmấy\b", "bao nhiêu"),
        (r"\bcó những\b", "gồm những"),
        (r"\bgồm những\b", "có những"),
        (r"\bnhư thế nào\b", "ra sao"),
        (r"\bra sao\b", "như thế nào"),
        (r"\bkhi nào\b", "vào thời điểm nào"),
        (r"\bở đâu\b", "ở chỗ nào"),
        (r"\blà gì\b", "cụ thể là gì"),
        (r"\bđược hiểu là gì\b", "có nghĩa là gì"),
        (r"\bđiều kiện\b", "điều kiện cụ thể"),
    ]

    for pattern, replacement in rewrite_rules:
        rewritten = replace_first_ci(base, pattern, replacement)
        if rewritten != base:
            candidates.append(f"{rewritten}?")

    clause = lower_first_for_clause(base)
    normalized_base = normalize_question(base)
    if not normalized_base.startswith("theo ") and not normalized_base.startswith("trong "):
        candidates.append(f"Theo {source}, {clause}?")
        candidates.append(f"Theo quy định trong {source}, {clause}?")
        candidates.append(f"Trong {source}, {clause}?")

    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        key = normalize_question(item)
        if key and key not in seen:
            deduped.append(item)
            seen.add(key)
    return deduped


def parse_question_file(text: str) -> tuple[dict[str, str], str, list[QuestionEntry]]:
    meta, body = split_frontmatter(text)
    first_question = re.search(r"^## Question \d+\s*$", body, flags=re.MULTILINE)
    if not first_question:
        return meta, body.strip(), []

    prefix = body[: first_question.start()].rstrip()
    question_blob = body[first_question.start() :]
    entries: list[QuestionEntry] = []
    for match in QUESTION_BLOCK_RE.finditer(question_blob):
        entries.append(
            QuestionEntry(
                source=match.group("source").strip(),
                question=match.group("question").strip(),
                answer=match.group("answer").strip(),
            )
        )
    return meta, prefix, entries


def even_sample(items: list[QuestionEntry], limit: int) -> list[QuestionEntry]:
    if limit <= 0 or len(items) <= limit:
        return items
    if limit == 1:
        return [items[len(items) // 2]]

    chosen: list[QuestionEntry] = []
    used_indices: set[int] = set()
    last_index = len(items) - 1
    for step in range(limit):
        index = round(step * last_index / (limit - 1))
        while index in used_indices and index < last_index:
            index += 1
        while index in used_indices and index > 0:
            index -= 1
        used_indices.add(index)
        chosen.append(items[index])
    return chosen


def build_rendered_body(prefix: str, entries: Iterable[QuestionEntry]) -> str:
    blocks: list[str] = [prefix.strip()]
    entry_list = list(entries)
    for index, entry in enumerate(entry_list, start=1):
        blocks.append(
            "\n".join(
                [
                    f"## Question {index:02d}",
                    "",
                    f"- `question_id`: `q{index:03d}`",
                    f"- `source`: `{entry.source}`",
                    "",
                    f"**Question:** {entry.question}",
                    "",
                    f"**Answer:** {entry.answer}",
                ]
            )
        )
    return "\n\n".join(part for part in blocks if part).strip() + "\n"


def expand_file(path: Path, *, max_new_per_file: int, dry_run: bool) -> tuple[int, int]:
    original = path.read_text(encoding="utf-8", errors="ignore")
    meta, prefix, entries = parse_question_file(original)
    if not entries:
        return 0, 0

    normalized_existing = {normalize_question(entry.question) for entry in entries}
    candidate_entries: list[QuestionEntry] = []

    for entry in entries:
        for candidate in candidate_variants(entry.question, entry.source):
            key = normalize_question(candidate)
            if not key or key in normalized_existing:
                continue
            normalized_existing.add(key)
            candidate_entries.append(
                QuestionEntry(source=entry.source, question=candidate, answer=entry.answer)
            )
            break

    selected = even_sample(candidate_entries, max_new_per_file)
    merged_entries = [*entries, *selected]

    base_name = path.name.replace(".questions.md", ".md")
    meta["source_context_file"] = f"data/primary_corpus/student_handbooks/{base_name}"
    meta["question_count"] = str(len(merged_entries))
    meta["generated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    previous_generator = meta.get("generator", "").strip()
    generator_tag = "expand_handbook_question_sets.py"
    if previous_generator:
        if generator_tag not in previous_generator:
            meta["generator"] = f"{previous_generator} + {generator_tag}"
    else:
        meta["generator"] = generator_tag

    updated = build_frontmatter(meta) + "\n\n" + build_rendered_body(prefix, merged_entries)
    if not dry_run and updated != original:
        path.write_text(updated, encoding="utf-8")
    return len(entries), len(selected)


def main() -> int:
    args = parse_args()
    root = args.root
    files = sorted(root.glob("*.questions.md"))
    if not files:
        raise SystemExit(f"Khong tim thay file .questions.md trong {root}")

    total_added = 0
    for path in files:
        before_count, added_count = expand_file(
            path,
            max_new_per_file=max(args.max_new_per_file, 0),
            dry_run=args.dry_run,
        )
        total_added += added_count
        action = "WOULD_UPDATE" if args.dry_run else "UPDATED"
        print(f"{action}: {path.name} | before={before_count} | added={added_count} | after={before_count + added_count}")

    print(f"Done. Added {total_added} question(s) across {len(files)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
