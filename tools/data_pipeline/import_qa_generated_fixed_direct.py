from __future__ import annotations

import argparse
from pathlib import Path
import sys


def _find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "main.py").exists() and (parent / "services").is_dir():
            return parent
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _find_repo_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.rag_tools import DEFAULT_RAG_TOOL, detect_tool_from_path
from config.settings import settings
from services.vector_store_service import add_documents, get_collection, reset_vectorstore


SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt"}


def iter_corpus_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )


def import_corpus(root: Path, *, reset_first: bool = False, dry_run: bool = False) -> tuple[int, int]:
    files = iter_corpus_files(root)
    if not files:
        raise FileNotFoundError(f"Khong tim thay file markdown trong: {root}")

    if dry_run:
        print(f"Dry run: tim thay {len(files)} file trong {root}")
        for path in files[:10]:
            print(f" - {path.relative_to(root).as_posix()}")
        if len(files) > 10:
            print(f" ... va {len(files) - 10} file khac")
        return len(files), 0

    if reset_first:
        reset_vectorstore()

    imported = 0
    collection = get_collection()
    before_count = collection.count()

    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        source_name = path.relative_to(root).as_posix()
        tool_name = detect_tool_from_path(path) or DEFAULT_RAG_TOOL
        add_documents(
            file_content=text,
            filename=path.name,
            source_name=source_name,
            tool_name=tool_name,
        )
        imported += 1
        print(f"Imported: {source_name}")

    after_count = collection.count()
    return imported, max(after_count - before_count, 0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bulk import seed corpus markdown vao Chroma vector store.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=settings.QA_CORPUS_ROOT,
        help="Thu muc corpus can import. Mac dinh: data/primary_corpus",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Xoa vector store hien tai truoc khi import.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chi liet ke file se import, khong ghi vao vector store.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = args.root.resolve()

    imported, added_chunks = import_corpus(
        root,
        reset_first=args.reset,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        print(f"San sang import {imported} file tu {root}")
    else:
        print(f"Hoan tat: {imported} file, tang them {added_chunks} chunk trong vector store")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
