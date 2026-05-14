"""
scripts/reindex_corpus.py
=========================
Re-index toàn bộ seed corpus vào ChromaDB vectorstore và xác minh
rằng mọi metadata trường quan trọng (section_title, chunk_id, source_path)
đều được ghi đầy đủ cho tất cả các chunk.

Sử dụng:
    python scripts/reindex_corpus.py                   # Re-index + verify
    python scripts/reindex_corpus.py --reset            # Reset vectorstore trước khi import
    python scripts/reindex_corpus.py --verify-only      # Chỉ verify, không import
    python scripts/reindex_corpus.py --include-uploads  # Bao gồm cả uploaded documents
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# ── Resolve project root ────────────────────────────────────────────
def _find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "main.py").exists() and (parent / "services").is_dir():
            return parent
    return Path(__file__).resolve().parents[1]


ROOT = _find_repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── Imports (after path setup) ──────────────────────────────────────
from repositories.vector_repository import get_vector_collection  # noqa: E402
from services.content.document_service import (  # noqa: E402
    import_seed_corpus,
    reingest_uploaded_documents,
)
from services.vector.vector_store_service import (  # noqa: E402
    embedding_backend_ready,
    get_collection,
)


# ── Metadata verification ──────────────────────────────────────────
REQUIRED_METADATA_FIELDS = [
    "section_title",
    "chunk_id",
    "source_path",
    "source",
    "file_name",
    "academic_year",
    "title",
    "tool_name",
    "document_type",
]


def verify_metadata(*, verbose: bool = False) -> dict:
    """Kiểm tra tất cả chunk trong vectorstore có đầy đủ metadata fields không."""
    collection = get_collection()
    total_chunks = collection.count()

    if total_chunks == 0:
        return {
            "status": "empty",
            "total_chunks": 0,
            "message": "Vector store trống — chưa có chunk nào.",
            "fields": {},
        }

    data = collection.get(include=["metadatas"])
    metadatas = data.get("metadatas", [])
    ids = data.get("ids", [])

    field_counts: dict[str, int] = {field: 0 for field in REQUIRED_METADATA_FIELDS}
    field_missing_examples: dict[str, list[str]] = {field: [] for field in REQUIRED_METADATA_FIELDS}

    for idx, meta in enumerate(metadatas):
        if not meta:
            for field in REQUIRED_METADATA_FIELDS:
                if len(field_missing_examples[field]) < 3:
                    field_missing_examples[field].append(ids[idx] if idx < len(ids) else f"index_{idx}")
            continue

        # Bỏ qua BOT_RULE chunk khi đếm
        if meta.get("source") == "BOT_RULE":
            total_chunks -= 1
            continue

        for field in REQUIRED_METADATA_FIELDS:
            value = meta.get(field)
            if value is not None and str(value).strip() not in ("", "-1"):
                field_counts[field] += 1
            elif len(field_missing_examples[field]) < 3:
                field_missing_examples[field].append(ids[idx] if idx < len(ids) else f"index_{idx}")

    all_pass = all(count == total_chunks for count in field_counts.values())

    fields_report = {}
    for field in REQUIRED_METADATA_FIELDS:
        count = field_counts[field]
        status = "✅ PASS" if count == total_chunks else "❌ FAIL"
        fields_report[field] = {
            "count": count,
            "total": total_chunks,
            "status": status,
            "missing_examples": field_missing_examples[field] if count < total_chunks else [],
        }

    return {
        "status": "pass" if all_pass else "fail",
        "total_chunks": total_chunks,
        "message": (
            f"✅ Tất cả {total_chunks} chunks có đầy đủ metadata."
            if all_pass
            else f"❌ Một số metadata fields chưa đầy đủ trên {total_chunks} chunks."
        ),
        "fields": fields_report,
    }


def print_verify_report(report: dict) -> None:
    """In báo cáo xác minh metadata ra console."""
    print("\n" + "=" * 70)
    print("📊 BÁO CÁO XÁC MINH METADATA VECTORSTORE")
    print("=" * 70)
    print(f"Tổng chunks (trừ BOT_RULE): {report['total_chunks']}")
    print(f"Trạng thái chung: {report['message']}")
    print()

    for field, info in report.get("fields", {}).items():
        count = info["count"]
        total = info["total"]
        status = info["status"]
        print(f"  {field:20s}  {count:>5}/{total:<5}  {status}")
        if info.get("missing_examples"):
            for example in info["missing_examples"][:3]:
                print(f"    └─ missing in: {example}")

    print("=" * 70)


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-index seed corpus vào ChromaDB và verify metadata."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset vectorstore trước khi import (xóa toàn bộ dữ liệu cũ).",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Chỉ chạy verify metadata, không import.",
    )
    parser.add_argument(
        "--include-uploads",
        action="store_true",
        help="Bao gồm cả uploaded documents khi re-ingest.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Ghi kết quả verify ra file JSON.",
    )
    args = parser.parse_args()

    if not args.verify_only:
        # ── Check embedding backend ──
        if not embedding_backend_ready():
            print("❌ Embedding backend chưa sẵn sàng!")
            print("   Kiểm tra kết nối internet hoặc local model cache.")
            sys.exit(1)

        # ── Get initial state ──
        initial_count = get_collection().count()
        print(f"📦 Vector store hiện có: {initial_count} chunks")

        # ── Re-index ──
        t0 = time.time()
        if args.include_uploads:
            print("\n🔄 Re-indexing toàn bộ (seed corpus + uploads)...")
            total_files, total_chunks = reingest_uploaded_documents()
            print(f"✅ Re-ingest xong: {total_files} files → {total_chunks} chunks mới")
        else:
            print(f"\n🔄 Import seed corpus (reset={args.reset})...")
            result = import_seed_corpus(reset_first=args.reset)
            print(f"   Status: {result['status']}")
            print(f"   Message: {result['msg']}")
            print(f"   Files: {result['imported_files']}/{result['total_files']}")
            print(f"   Chunks: {result['total_chunks']}")

        elapsed = time.time() - t0
        print(f"\n⏱️  Thời gian re-index: {elapsed:.1f}s")

    # ── Verify ──
    print("\n🔍 Đang xác minh metadata...")
    report = verify_metadata()
    print_verify_report(report)

    # ── Output JSON ──
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n📝 Đã ghi báo cáo JSON: {args.output_json}")

    # ── Exit code ──
    if report["status"] == "fail":
        print("\n⚠️  Một số metadata fields chưa đầy đủ — xem báo cáo ở trên.")
        sys.exit(1)
    elif report["status"] == "empty":
        print("\n⚠️  Vector store trống.")
        sys.exit(1)
    else:
        print("\n✅ Tất cả metadata đã đồng bộ thành công!")


if __name__ == "__main__":
    main()
