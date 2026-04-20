#!/usr/bin/env python
# Usage:
#   python sync_clean_data_to_qa.py
#   python sync_clean_data_to_qa.py --source-root clean_data --target-root data/qa_generated_fixed
#   python sync_clean_data_to_qa.py --apply
#   python sync_clean_data_to_qa.py --apply --yes --limit 10 --verbose

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


SCRIPT_NAME = "sync_clean_data_to_qa.py"
SYNC_SECTION_HEADING = "## Nguon toan van"
SYNC_BEGIN_MARKER = "<!-- sync_clean_data_to_qa:begin -->"
SYNC_END_MARKER = "<!-- sync_clean_data_to_qa:end -->"
DEFAULT_SOURCE_ROOT = Path("clean_data")
DEFAULT_TARGET_ROOT = Path("data/qa_generated_fixed")
DEFAULT_REPORT_PATH = Path("reports/generated/clean_to_qa_sync_report.json")


@dataclass
class FileAudit:
    relative_path: str
    status: str
    source_chars: int
    target_chars: int
    target_main_chars: int
    synced_chars: int
    coverage_ratio: float
    note: str = ""


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
        description=(
            "Doi chieu clean_data voi data/qa_generated_fixed, bao cao file thieu noi dung "
            "va co the chen them nguon toan van vao file QA."
        )
    )
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT, help="Thu muc markdown nguon day du.")
    parser.add_argument("--target-root", type=Path, default=DEFAULT_TARGET_ROOT, help="Thu muc markdown QA can doi chieu.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH, help="Noi ghi bao cao JSON.")
    parser.add_argument("--apply", action="store_true", help="Ghi cap nhat vao target files sau khi doi chieu.")
    parser.add_argument("--yes", action="store_true", help="Bo qua prompt xac nhan khi dung --apply.")
    parser.add_argument("--include-pending", action="store_true", help="Bao gom file trong _ocr_pending.")
    parser.add_argument("--limit", type=int, default=None, help="Chi xu ly N file dau tien.")
    parser.add_argument("--verbose", action="store_true", help="In chi tiet tung file.")
    return parser.parse_args()


def split_front_matter(text: str) -> tuple[str, str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---\n"):
        return "", normalized

    end_marker = normalized.find("\n---\n", 4)
    if end_marker == -1:
        return "", normalized

    front_matter = normalized[: end_marker + 5]
    body = normalized[end_marker + 5 :].lstrip("\n")
    return front_matter, body


def normalize_body(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


SYNC_BLOCK_PATTERN = re.compile(
    rf"\n*{re.escape(SYNC_SECTION_HEADING)}\s*\n+{re.escape(SYNC_BEGIN_MARKER)}\n(?P<content>.*?)\n{re.escape(SYNC_END_MARKER)}\n*",
    flags=re.DOTALL,
)


def split_synced_block(body: str) -> tuple[str, str]:
    match = SYNC_BLOCK_PATTERN.search(body)
    if not match:
        return normalize_body(body), ""

    synced_content = normalize_body(match.group("content"))
    body_without_sync = body[: match.start()] + body[match.end() :]
    return normalize_body(body_without_sync), synced_content


def iter_markdown_files(root: Path, *, include_pending: bool) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*.md"), key=lambda item: str(item).lower()):
        if not include_pending and "_ocr_pending" in path.parts:
            continue
        if path.is_file():
            files.append(path)
    return files


def condensed_text(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()


def build_synced_section(source_body: str) -> str:
    return "\n".join(
        [
            SYNC_SECTION_HEADING,
            "",
            SYNC_BEGIN_MARKER,
            source_body.strip(),
            SYNC_END_MARKER,
        ]
    ).strip()


def rebuild_markdown(front_matter: str, body: str) -> str:
    normalized_body = normalize_body(body)
    if front_matter:
        return front_matter.rstrip() + "\n\n" + normalized_body + "\n"
    return normalized_body + "\n"


def target_already_contains_source(target_main_body: str, source_body: str) -> bool:
    source_compact = condensed_text(source_body)
    target_compact = condensed_text(target_main_body)
    if not source_compact or not target_compact:
        return False

    probe = source_compact[: min(len(source_compact), 800)]
    return bool(probe) and probe in target_compact


def audit_file(source_path: Path, target_path: Path, source_root: Path) -> FileAudit:
    relative_path = source_path.relative_to(source_root).as_posix()
    source_text = source_path.read_text(encoding="utf-8", errors="ignore")
    _, source_body_raw = split_front_matter(source_text)
    source_body = normalize_body(source_body_raw)

    if not source_body:
        return FileAudit(
            relative_path=relative_path,
            status="empty_source",
            source_chars=0,
            target_chars=0,
            target_main_chars=0,
            synced_chars=0,
            coverage_ratio=0.0,
            note="Source file has no body content.",
        )

    if not target_path.exists():
        return FileAudit(
            relative_path=relative_path,
            status="missing_target",
            source_chars=len(source_body),
            target_chars=0,
            target_main_chars=0,
            synced_chars=0,
            coverage_ratio=0.0,
            note="Target file does not exist.",
        )

    target_text = target_path.read_text(encoding="utf-8", errors="ignore")
    _, target_body_raw = split_front_matter(target_text)
    target_main_body, synced_body = split_synced_block(target_body_raw)
    coverage_ratio = len(target_main_body) / max(len(source_body), 1)

    if synced_body == source_body:
        status = "up_to_date"
        note = "Synced source section is already current."
    elif synced_body:
        status = "needs_refresh"
        note = "Existing synced source section differs from clean_data."
    elif target_already_contains_source(target_main_body, source_body):
        status = "up_to_date"
        note = "Target body already appears to include source content."
    else:
        status = "needs_sync"
        note = "QA body is shorter than source and has no synced full-text section."

    return FileAudit(
        relative_path=relative_path,
        status=status,
        source_chars=len(source_body),
        target_chars=len(normalize_body(target_body_raw)),
        target_main_chars=len(target_main_body),
        synced_chars=len(synced_body),
        coverage_ratio=round(coverage_ratio, 3),
        note=note,
    )


def build_updated_target_text(source_path: Path, target_path: Path) -> str:
    source_text = source_path.read_text(encoding="utf-8", errors="ignore")
    target_text = target_path.read_text(encoding="utf-8", errors="ignore")

    _, source_body_raw = split_front_matter(source_text)
    source_body = normalize_body(source_body_raw)

    target_front_matter, target_body_raw = split_front_matter(target_text)
    target_main_body, _ = split_synced_block(target_body_raw)

    updated_body_parts = [target_main_body.strip(), build_synced_section(source_body)]
    updated_body = "\n\n".join(part for part in updated_body_parts if part.strip())
    return rebuild_markdown(target_front_matter, updated_body)


def summarise_statuses(items: list[FileAudit]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in items:
        summary[item.status] = summary.get(item.status, 0) + 1
    return dict(sorted(summary.items(), key=lambda pair: pair[0]))


def write_report(
    report_path: Path,
    *,
    source_root: Path,
    target_root: Path,
    items: list[FileAudit],
    extra_target_files: list[str],
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "script": SCRIPT_NAME,
        "source_root": str(source_root),
        "target_root": str(target_root),
        "summary": summarise_statuses(items),
        "extra_target_files": extra_target_files,
        "files": [asdict(item) for item in items],
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def confirm_apply(items_to_update: list[FileAudit]) -> bool:
    safe_print("")
    safe_print(f"Se cap nhat {len(items_to_update)} file trong target corpus.")
    reply = input("Ban co muon tiep tuc khong? [y/N]: ").strip().lower()
    return reply in {"y", "yes"}


def main() -> int:
    args = parse_args()
    source_root = args.source_root.resolve()
    target_root = args.target_root.resolve()
    report_path = args.report.resolve()

    if not source_root.exists():
        safe_print(f"Source root does not exist: {source_root}", error=True)
        return 1

    if not target_root.exists():
        safe_print(f"Target root does not exist: {target_root}", error=True)
        return 1

    source_files = iter_markdown_files(source_root, include_pending=args.include_pending)
    if args.limit is not None:
        source_files = source_files[: max(args.limit, 0)]

    if not source_files:
        safe_print("Khong tim thay file markdown nao de doi chieu.", error=True)
        return 1

    audits: list[FileAudit] = []
    source_relatives: set[str] = set()
    for source_path in source_files:
        relative_path = source_path.relative_to(source_root).as_posix()
        source_relatives.add(relative_path)
        target_path = target_root / source_path.relative_to(source_root)
        audit = audit_file(source_path, target_path, source_root)
        audits.append(audit)
        if args.verbose:
            safe_print(
                f"[{audit.status}] {audit.relative_path} | "
                f"source={audit.source_chars} target_main={audit.target_main_chars} "
                f"synced={audit.synced_chars} ratio={audit.coverage_ratio}"
            )

    extra_target_files = [
        path.relative_to(target_root).as_posix()
        for path in iter_markdown_files(target_root, include_pending=True)
        if path.relative_to(target_root).as_posix() not in source_relatives
    ]
    write_report(
        report_path,
        source_root=source_root,
        target_root=target_root,
        items=audits,
        extra_target_files=extra_target_files,
    )

    summary = summarise_statuses(audits)
    safe_print("")
    safe_print("Summary")
    safe_print(f"- Source files checked: {len(audits)}")
    safe_print(f"- Report written: {report_path}")
    for status, count in summary.items():
        safe_print(f"- {status}: {count}")
    safe_print(f"- Extra target files without matching clean_data source: {len(extra_target_files)}")

    items_to_update = [item for item in audits if item.status in {"needs_sync", "needs_refresh"}]
    missing_targets = [item for item in audits if item.status == "missing_target"]

    if missing_targets:
        safe_print(f"- Missing target files: {len(missing_targets)}")

    if not args.apply:
        safe_print("")
        safe_print("Dry run only. Dung --apply de chen them nguon toan van vao target files can dong bo.")
        return 0

    if not items_to_update:
        safe_print("")
        safe_print("Khong co file nao can cap nhat.")
        return 0

    if not args.yes and not confirm_apply(items_to_update):
        safe_print("Da huy cap nhat.")
        return 0

    updated = 0
    for item in items_to_update:
        source_path = source_root / Path(item.relative_path)
        target_path = target_root / Path(item.relative_path)
        updated_text = build_updated_target_text(source_path, target_path)
        target_path.write_text(updated_text, encoding="utf-8")
        updated += 1
        if args.verbose:
            safe_print(f"Updated: {item.relative_path}")

    safe_print("")
    safe_print(f"Hoan tat cap nhat {updated} file.")
    if missing_targets:
        safe_print(
            "Luu y: mot so file chi co trong clean_data nhung chua co file doi ung trong target. "
            "Xem report JSON de xu ly tiep."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
