from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Callable


def iter_importable_paths(root: Path, *, supported_suffixes: set[str]) -> list[Path]:
    if not root.exists():
        return []

    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in supported_suffixes
    )


def iter_seed_source_records(
    root: Path,
    *,
    default_tool: str,
    detect_tool_from_path: Callable[[Path], str | None],
    supported_suffixes: set[str],
) -> list[tuple[Path, str, str]]:
    records: list[tuple[Path, str, str]] = []
    for path in iter_importable_paths(root, supported_suffixes=supported_suffixes):
        try:
            source_name = path.relative_to(root).as_posix()
        except ValueError:
            source_name = path.name
        tool_name = detect_tool_from_path(path) or default_tool
        records.append((path, tool_name, source_name))
    return records


def iter_uploaded_source_records(
    *,
    rag_tool_order: list[str],
    get_tool_upload_dir: Callable[[str], Path],
    build_upload_source_name: Callable[[str, str], str],
    upload_dir: Path,
    default_tool: str,
    supported_suffixes: set[str],
) -> list[tuple[Path, str, str]]:
    records: list[tuple[Path, str, str]] = []

    for tool_name in rag_tool_order:
        for path in iter_importable_paths(get_tool_upload_dir(tool_name), supported_suffixes=supported_suffixes):
            records.append((path, tool_name, build_upload_source_name(tool_name, path.name)))

    for path in iter_importable_paths(upload_dir, supported_suffixes=supported_suffixes):
        records.append((path, default_tool, path.name))

    return records


def build_vector_tool_groups(
    chunks_by_file: dict[str, list[dict[str, Any]]],
    *,
    rag_tool_order: list[str],
    rag_tool_profiles: dict[str, dict[str, Any]],
    infer_vector_tool_name: Callable[[str, str | None], str | None],
    is_valid_rag_tool: Callable[[str | None], bool],
    display_vector_source: Callable[[str], str],
    upload_source_prefix: str,
    limit_per_file: int,
) -> list[dict[str, Any]]:
    grouped_sources: dict[str, dict[str, list[dict[str, Any]]]] = {tool_name: {} for tool_name in rag_tool_order}
    theme_by_tool = {
        "student_handbook_rag": "orange",
        "school_policy_rag": "purple",
        "student_faq_rag": "teal",
    }

    for source, chunks in chunks_by_file.items():
        if not chunks:
            continue

        tool_name = infer_vector_tool_name(source, chunks[0].get("tool_name"))
        if not is_valid_rag_tool(tool_name):
            continue
        grouped_sources.setdefault(str(tool_name), {})[source] = chunks

    tool_groups: list[dict[str, Any]] = []
    for tool_name in rag_tool_order:
        file_items: list[dict[str, Any]] = []
        total_chunks = 0

        for source, items in sorted(grouped_sources.get(tool_name, {}).items(), key=lambda item: item[0]):
            sorted_items = sorted(items, key=lambda chunk: chunk["level"], reverse=True)
            is_upload_source = str(source).replace("\\", "/").startswith(f"{upload_source_prefix}/")
            total_chunks += len(sorted_items)
            file_items.append(
                {
                    "source": source,
                    "display_name": display_vector_source(source),
                    "source_label": source,
                    "chunk_count": len(sorted_items),
                    "chunks": sorted_items[:limit_per_file],
                    "tool_name": tool_name,
                    "is_upload_source": is_upload_source,
                    "source_kind_label": "File upload" if is_upload_source else "Seed corpus",
                }
            )

        profile = rag_tool_profiles[tool_name]
        tool_groups.append(
            {
                "name": tool_name,
                "label": str(profile.get("label", tool_name)),
                "description": str(profile.get("description", "")),
                "theme": theme_by_tool.get(tool_name, "teal"),
                "total_files": len(file_items),
                "total_chunks": total_chunks,
                "files": file_items,
            }
        )

    return tool_groups


def build_vector_manager_summary(
    data: dict[str, list[Any]],
    *,
    rag_tool_order: list[str],
    rag_tool_profiles: dict[str, dict[str, Any]],
    infer_vector_tool_name: Callable[[str, str | None], str | None],
    is_valid_rag_tool: Callable[[str | None], bool],
    display_vector_source: Callable[[str], str],
    upload_source_prefix: str,
    limit_per_file: int,
) -> dict[str, Any]:
    chunks_by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    ids = data.get("ids", [])
    documents = data.get("documents", [])
    metadatas = data.get("metadatas", [])
    if not isinstance(ids, list) or not isinstance(documents, list) or not isinstance(metadatas, list):
        raise ValueError("Vector store payload must provide list values for ids, documents, and metadatas.")
    if not (len(ids) == len(documents) == len(metadatas)):
        raise ValueError(
            f"Mismatched vector payload lengths: ids={len(ids)}, documents={len(documents)}, metadatas={len(metadatas)}"
        )

    for doc_id, doc, meta in zip(ids, documents, metadatas):
        source = meta.get("source", "unknown.md")
        doc_text = str(doc or "").strip()
        doc_words = doc_text.split()
        preview_text = " ".join(doc_words[:30])
        if len(doc_words) > 30:
            preview_text += "..."

        chunks_by_file[source].append(
            {
                "id": doc_id,
                "chunk_id": meta.get("chunk_id", doc_id),
                "content": doc_text,
                "preview": preview_text,
                "title": meta.get("title", "Không có tiêu đề"),
                "level": meta.get("level", 1),
                "word_count": meta.get("word_count", len(doc_words)),
                "tool_name": meta.get("tool_name", "unassigned"),
                "academic_year": meta.get("academic_year", ""),
                "chapter": meta.get("chapter", ""),
                "section": meta.get("section", ""),
                "section_title": meta.get("section_title", meta.get("title", "")),
                "source_path": meta.get("source_path", source),
                "page_number": meta.get("page_number", -1),
                "document_type": meta.get("document_type", ""),
            }
        )

    tool_groups = build_vector_tool_groups(
        dict(chunks_by_file),
        rag_tool_order=rag_tool_order,
        rag_tool_profiles=rag_tool_profiles,
        infer_vector_tool_name=infer_vector_tool_name,
        is_valid_rag_tool=is_valid_rag_tool,
        display_vector_source=display_vector_source,
        upload_source_prefix=upload_source_prefix,
        limit_per_file=limit_per_file,
    )
    visible_chunks_by_file = {
        file_item["source"]: file_item["chunks"]
        for group in tool_groups
        for file_item in group["files"]
    }
    return {
        "chunks_by_file": visible_chunks_by_file,
        "total_chunks": sum(group["total_chunks"] for group in tool_groups),
        "total_files": sum(group["total_files"] for group in tool_groups),
        "tool_groups": tool_groups,
    }


def reingest_source_records(
    source_records: list[tuple[Path, str, str]],
    *,
    reset_vectorstore: Callable[[], None],
    get_collection: Callable[[], Any],
    add_documents: Callable[..., None],
    clear_rag_corpus_cache: Callable[[], None],
) -> tuple[int, int]:
    if not source_records:
        return 0, 0

    reset_vectorstore()
    total_files = 0
    total_chunks = 0

    for path, tool_name, source_name in source_records:
        try:
            before_count = get_collection().count()
            text = path.read_text(encoding="utf-8", errors="ignore")
            add_documents(
                file_content=text,
                filename=path.name,
                source_name=source_name,
                tool_name=tool_name,
            )
            total_files += 1
            total_chunks += max(get_collection().count() - before_count, 0)
        except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
            print(f"Re-ingest lỗi {path.name}: {exc}")

    clear_rag_corpus_cache()
    return total_files, total_chunks
