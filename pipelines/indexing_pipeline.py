from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional


def build_chunk_id_prefix(source_name: str) -> str:
    import hashlib

    digest = hashlib.sha1(source_name.encode("utf-8", errors="ignore")).hexdigest()[:12]
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", source_name).strip("_") or "document"
    return f"{safe_name}__{digest}"


def index_document(
    *,
    file_content: str,
    filename: str,
    version: str,
    source_name: Optional[str],
    tool_name: Optional[str],
    collection_getter: Callable[[], Any],
    smart_chunk_fn: Callable[[str, str, Optional[str]], list[dict[str, Any]]],
    extract_academic_year_fn: Callable[[str, str, str], Optional[str]],
    infer_document_type_fn: Callable[[str, str, Optional[str], str], str],
    rebuild_bm25_fn: Callable[[], None],
    inject_bot_rule_fn: Callable[..., None],
) -> None:
    collection = collection_getter()
    clean_name = (source_name or Path(filename).name).strip()
    if not clean_name:
        clean_name = Path(filename).name or "document.md"

    selected_tool_name = str(tool_name or "unassigned")
    academic_year = extract_academic_year_fn(clean_name, filename, file_content)
    document_type = infer_document_type_fn(clean_name, filename, selected_tool_name, file_content)
    chunks = smart_chunk_fn(file_content, filename, clean_name)
    if not chunks:
        print(f"No chunks generated from {filename}")
        return

    collection.delete(where={"source": clean_name})

    documents = [chunk["text"] for chunk in chunks]
    id_prefix = build_chunk_id_prefix(clean_name)
    ids = [f"{id_prefix}__{index:05d}" for index in range(len(chunks))]
    metadatas = [
        {
            "source": clean_name,
            "source_path": clean_name,
            "title": chunk["title"],
            "title_clean": re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", chunk["title"].lower())).strip(),
            "level": chunk.get("level", 1),
            "chunk_type": chunk["type"],
            "token_count": chunk["token_count"],
            "word_count": chunk.get("word_count", len(chunk["text"].split())),
            "file_name": Path(clean_name).name,
            "academic_year": academic_year or "",
            "chunk_id": ids[index],
            "chapter": chunk.get("chapter", ""),
            "section": chunk.get("section", chunk.get("title", "")),
            "section_title": chunk.get("title", ""),
            "page_number": chunk.get("page_number") if chunk.get("page_number") is not None else -1,
            "document_type": document_type,
            "created_at": datetime.now().isoformat(),
            "version": version,
            "tool_name": selected_tool_name,
        }
        for index, chunk in enumerate(chunks)
    ]

    batch_size = 50
    for start in range(0, len(documents), batch_size):
        collection.add(
            documents=documents[start : start + batch_size],
            metadatas=metadatas[start : start + batch_size],
            ids=ids[start : start + batch_size],
        )

    print(f"Added {len(chunks)} chunks from {clean_name} (version {version})")
    rebuild_bm25_fn()
    inject_bot_rule_fn()
