from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Optional
import re

from config.rag_tools import (
    DEFAULT_RAG_TOOL,
    RAG_TOOL_ORDER,
    RAG_TOOL_PROFILES,
    UPLOAD_SOURCE_PREFIX,
    detect_tool_from_path,
    get_tool_upload_dir,
    is_valid_rag_tool,
)
from config.settings import settings
from pipelines.knowledge_base_pipeline import (
    build_approved_chat_markdown as build_approved_chat_markdown_from_pipeline,
    display_timestamp as display_timestamp_from_pipeline,
    group_chat_entries as group_chat_entries_from_pipeline,
    group_vector_entries as group_vector_entries_from_pipeline,
    load_vector_entries as load_vector_entries_from_pipeline,
    pair_chat_rows as pair_chat_rows_from_pipeline,
    search_chat_entries as search_chat_entries_from_pipeline,
    search_vector_entries as search_vector_entries_from_pipeline,
)
from repositories.conversation_repository import list_chat_history_rows
from repositories.knowledge_base_repository import (
    list_approved_chat_entry_ids,
    list_approved_chat_qas,
    save_approved_chat_qa,
)
from repositories.vector_repository import list_vector_chunks
from shared.text_utils import normalize_search_text, tokenize_search_text
from shared.vector_utils import display_vector_source, infer_vector_tool_name
from services.rag.ictu_scope_service import ICTU_SCOPE_REPLY_VI, is_ictu_related_query
from services.rag.rag_corpus import clear_rag_corpus_cache
from services.vector.vector_store_service import add_documents, embedding_backend_ready


MAX_VECTOR_CONTENT_CHARS = 7000
MAX_CHAT_SNIPPET_CHARS = 700
MAX_VECTOR_SNIPPET_CHARS = 700
APPROVED_CHAT_SUBDIR = "_knowledge_base_chat"
get_approved_chat_entry_ids = list_approved_chat_entry_ids
get_approved_chat_qas = list_approved_chat_qas
upsert_approved_chat_qa = save_approved_chat_qa


@dataclass(slots=True)
class VectorKnowledgeEntry:
    source: str
    display_name: str
    tool_name: str
    tool_label: str
    chunk_count: int
    titles: list[str]
    preview: str
    content: str


@dataclass(slots=True)
class ChatKnowledgeEntry:
    entry_id: str
    question_row_id: int
    answer_row_id: int
    session_id: str
    question: str
    answer: str
    timestamp: str
    time_label: str
    preview: str
    content: str
    is_approved: bool = False


def _normalize_search_text(text: str) -> str:
    return normalize_search_text(text)



def _tokenize_query(query: str) -> list[str]:
    return tokenize_search_text(query)



def _score_text_match(query: str, *, title: str, body: str, source: str) -> int:
    query_tokens = _tokenize_query(query)
    if not query_tokens:
        return 0

    normalized_title = _normalize_search_text(title)
    normalized_body = _normalize_search_text(body)
    normalized_source = _normalize_search_text(source)

    score = 0
    for token in set(query_tokens):
        if token in normalized_title:
            score += 7
        if token in normalized_source:
            score += 5
        if token in normalized_body:
            score += 3

    phrase = _normalize_search_text(query)
    if phrase and phrase in normalized_title:
        score += 12
    if phrase and phrase in normalized_source:
        score += 10
    if phrase and phrase in normalized_body:
        score += 8

    return score


def _build_match_snippet(body: str, query: str, max_chars: int) -> str:
    compact_body = re.sub(r"\s+", " ", body).strip()
    if len(compact_body) <= max_chars:
        return compact_body

    normalized_body = compact_body.casefold()
    normalized_query = _normalize_search_text(query)
    if normalized_query:
        match_at = normalized_body.find(normalized_query)
        if match_at >= 0:
            start = max(match_at - (max_chars // 3), 0)
            end = min(start + max_chars, len(compact_body))
            snippet = compact_body[start:end].strip()
            if start > 0:
                snippet = "... " + snippet
            if end < len(compact_body):
                snippet = snippet + " ..."
            return snippet

    return compact_body[:max_chars].rstrip() + " ..."


def _display_timestamp(raw_timestamp: str) -> str:
    return display_timestamp_from_pipeline(raw_timestamp)


def _fetch_chat_rows() -> list[dict]:
    return list_chat_history_rows()


def _build_chat_entry_id(session_id: str, answer_row_id: int) -> str:
    return f"chat::{session_id}::{answer_row_id}"


def _pair_chat_rows(rows: list[dict]) -> list[ChatKnowledgeEntry]:
    return pair_chat_rows_from_pipeline(
        rows,
        max_chat_snippet_chars=MAX_CHAT_SNIPPET_CHARS,
        build_chat_entry_id=_build_chat_entry_id,
        entry_factory=ChatKnowledgeEntry,
    )
    pending_question_by_session: dict[str, deque[dict]] = defaultdict(deque)
    pairs: list[ChatKnowledgeEntry] = []

    for row in rows:
        role = str(row.get("role", "")).strip().lower()
        session_id = str(row.get("session_id") or "default").strip() or "default"
        content = str(row.get("content") or "").strip()
        if not content:
            continue

        if role == "user":
            pending_question_by_session[session_id].append(row)
            continue

        if role not in {"bot", "assistant"}:
            continue

        pending_queue = pending_question_by_session.get(session_id)
        if not pending_queue:
            continue
        pending = pending_queue.popleft()
        if not pending_queue:
            pending_question_by_session.pop(session_id, None)

        question = str(pending.get("content") or "").strip()
        answer = content
        if not question or not answer:
            continue

        timestamp = str(row.get("timestamp") or pending.get("timestamp") or "")
        preview = re.sub(r"\s+", " ", answer)
        if len(preview) > MAX_CHAT_SNIPPET_CHARS:
            preview = preview[:MAX_CHAT_SNIPPET_CHARS].rstrip() + " ..."

        question_row_id = int(pending.get("id") or 0)
        answer_row_id = int(row.get("id") or 0)
        pairs.append(
            ChatKnowledgeEntry(
                entry_id=_build_chat_entry_id(session_id, answer_row_id),
                question_row_id=question_row_id,
                answer_row_id=answer_row_id,
                session_id=session_id,
                question=question,
                answer=answer,
                timestamp=timestamp,
                time_label=_display_timestamp(timestamp),
                preview=preview,
                content=f"Q: {question}\nA: {answer}",
            )
        )

    pairs.sort(key=lambda item: (item.timestamp, item.entry_id), reverse=True)
    return pairs


def _load_chat_entries() -> list[ChatKnowledgeEntry]:
    try:
        approved_entry_ids = get_approved_chat_entry_ids()
    except Exception:
        approved_entry_ids = set()
    entries = _pair_chat_rows(_fetch_chat_rows())
    for entry in entries:
        entry.is_approved = entry.entry_id in approved_entry_ids
    return entries


def get_chat_entry_by_id(entry_id: str) -> Optional[ChatKnowledgeEntry]:
    for entry in _load_chat_entries():
        if entry.entry_id == entry_id:
            return entry
    return None


def _slugify_text(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _normalize_search_text(text))
    return slug.strip("-") or "qa"


def _approved_chat_filename(entry: ChatKnowledgeEntry) -> str:
    stem = _slugify_text(entry.question)[:48]
    return f"approved-chat-{entry.answer_row_id}-{stem}.md"


def _approved_chat_source_name(tool_name: str, filename: str) -> str:
    return PurePosixPath(UPLOAD_SOURCE_PREFIX, tool_name, APPROVED_CHAT_SUBDIR, filename).as_posix()


def _build_approved_chat_markdown(entry: ChatKnowledgeEntry, tool_name: str) -> str:
    return build_approved_chat_markdown_from_pipeline(entry, tool_name)
    title = f"Approved Chat QA - {entry.question[:120]}"
    approved_at = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        "---",
        f'title: "{title.replace(chr(34), chr(39))}"',
        f'source_entry_id: "{entry.entry_id}"',
        f'session_id: "{entry.session_id}"',
        f'tool_name: "{tool_name}"',
        f'approved_at: "{approved_at}"',
        f'generator: "knowledge_base_service.approve_chat_entry"',
        "---",
        "",
        f"# {title}",
        "",
        "## Câu hỏi",
        "",
        entry.question.strip(),
        "",
        "## Trả lời đã duyệt",
        "",
        entry.answer.strip(),
        "",
        "## Ghi chu",
        "",
        "- Nguồn này được tạo từ cặp hỏi đáp chatbot đã duyệt thủ công.",
        "- Có thể được đồng bộ vào vector store để dùng lại trong retrieval.",
        "",
    ]
    return "\n".join(lines)


def approve_chat_entry(entry_id: str, tool_name: str = DEFAULT_RAG_TOOL) -> dict:
    entry = get_chat_entry_by_id(entry_id)
    if entry is None:
        raise ValueError("Không tìm thấy cặp hỏi đáp chatbot để duyệt.")

    selected_tool = tool_name if is_valid_rag_tool(tool_name) else DEFAULT_RAG_TOOL
    filename = _approved_chat_filename(entry)
    storage_path = get_tool_upload_dir(selected_tool) / APPROVED_CHAT_SUBDIR / filename
    source_name = _approved_chat_source_name(selected_tool, filename)
    markdown = _build_approved_chat_markdown(entry, selected_tool)

    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_text(markdown, encoding="utf-8")

    upsert_approved_chat_qa(
        entry_id=entry.entry_id,
        question_row_id=entry.question_row_id,
        answer_row_id=entry.answer_row_id,
        session_id=entry.session_id,
        tool_name=selected_tool,
        question=entry.question,
        answer=entry.answer,
        source_name=source_name,
        storage_path=str(storage_path),
    )

    indexed = False
    warning = ""
    if embedding_backend_ready():
        try:
            add_documents(
                file_content=markdown,
                filename=filename,
                source_name=source_name,
                tool_name=selected_tool,
            )
            indexed = True
        except Exception as exc:
            warning = f"Đã lưu Q&A đã duyệt nhưng chưa index được vào vector store: {exc}"
    else:
        warning = "Đã lưu Q&A đã duyệt vào knowledge base, nhưng embedding backend chưa sẵn sàng để index."

    clear_rag_corpus_cache()
    return {
        "entry_id": entry.entry_id,
        "tool_name": selected_tool,
        "filename": filename,
        "source_name": source_name,
        "storage_path": str(storage_path),
        "indexed": indexed,
        "warning": warning,
        "message": (
            "Đã duyệt Q&A vào knowledge base và index vector store."
            if indexed
            else "Đã duyệt Q&A vào knowledge base."
        ),
    }


def _load_vector_entries() -> tuple[list[VectorKnowledgeEntry], int]:
    return load_vector_entries_from_pipeline(
        list_vector_chunks(),
        default_rag_tool=DEFAULT_RAG_TOOL,
        rag_tool_profiles=RAG_TOOL_PROFILES,
        infer_vector_tool_name=infer_vector_tool_name,
        display_vector_source=display_vector_source,
        max_vector_content_chars=MAX_VECTOR_CONTENT_CHARS,
        max_vector_snippet_chars=MAX_VECTOR_SNIPPET_CHARS,
        entry_factory=VectorKnowledgeEntry,
    )
    raw = list_vector_chunks()

    grouped: dict[str, dict] = {}
    total_chunks = 0

    for document, metadata in zip(raw.get("documents", []), raw.get("metadatas", [])):
        source = str((metadata or {}).get("source", "")).strip()
        if not source or source == "BOT_RULE":
            continue

        total_chunks += 1
        bucket = grouped.setdefault(
            source,
            {
                "source": source,
                "tool_name": infer_vector_tool_name(source, (metadata or {}).get("tool_name")) or DEFAULT_RAG_TOOL,
                "titles": [],
                "documents": [],
            },
        )

        title = str((metadata or {}).get("title", "")).strip()
        if title:
            bucket["titles"].append(title)
        bucket["documents"].append(str(document or "").strip())

    entries: list[VectorKnowledgeEntry] = []
    for source, bucket in grouped.items():
        tool_name = str(bucket["tool_name"])
        tool_label = str(RAG_TOOL_PROFILES.get(tool_name, {}).get("label", tool_name))
        combined_content = "\n\n".join(piece for piece in bucket["documents"] if piece).strip()
        if len(combined_content) > MAX_VECTOR_CONTENT_CHARS:
            combined_content = combined_content[:MAX_VECTOR_CONTENT_CHARS].rstrip() + " ..."

        preview = re.sub(r"\s+", " ", combined_content)
        if len(preview) > MAX_VECTOR_SNIPPET_CHARS:
            preview = preview[:MAX_VECTOR_SNIPPET_CHARS].rstrip() + " ..."

        unique_titles = list(dict.fromkeys(title for title in bucket["titles"] if title))
        entries.append(
            VectorKnowledgeEntry(
                source=source,
                display_name=display_vector_source(source),
                tool_name=tool_name,
                tool_label=tool_label,
                chunk_count=len(bucket["documents"]),
                titles=unique_titles[:8],
                preview=preview,
                content=combined_content,
            )
        )

    entries.sort(key=lambda item: (item.tool_label.casefold(), item.display_name.casefold()))
    return entries, total_chunks


def _group_vector_entries(entries: list[VectorKnowledgeEntry], limit_per_tool: int = 8) -> list[dict]:
    return group_vector_entries_from_pipeline(
        entries,
        rag_tool_order=RAG_TOOL_ORDER,
        rag_tool_profiles=RAG_TOOL_PROFILES,
        limit_per_tool=limit_per_tool,
    )
    grouped: dict[str, list[VectorKnowledgeEntry]] = defaultdict(list)
    for entry in entries:
        grouped[entry.tool_name].append(entry)

    payload: list[dict] = []
    for tool_name in RAG_TOOL_ORDER:
        items = grouped.get(tool_name, [])
        profile = RAG_TOOL_PROFILES.get(tool_name, {})
        payload.append(
            {
                "name": tool_name,
                "label": str(profile.get("label", tool_name)),
                "description": str(profile.get("description", "")),
                "total_files": len(items),
                "total_chunks": sum(item.chunk_count for item in items),
                "files": [
                    {
                        "source": item.source,
                        "display_name": item.display_name,
                        "preview": item.preview,
                        "chunk_count": item.chunk_count,
                        "titles": item.titles,
                    }
                    for item in items[:limit_per_tool]
                ],
            }
        )

    return payload


def _group_chat_entries(entries: list[ChatKnowledgeEntry], limit_per_session: int = 6) -> list[dict]:
    return group_chat_entries_from_pipeline(entries, limit_per_session=limit_per_session)
    grouped: dict[str, list[ChatKnowledgeEntry]] = defaultdict(list)
    for entry in entries:
        grouped[entry.session_id].append(entry)

    session_groups: list[dict] = []
    for session_id, items in sorted(grouped.items(), key=lambda pair: pair[0].casefold()):
        sorted_items = sorted(items, key=lambda item: (item.timestamp, item.entry_id), reverse=True)
        session_groups.append(
            {
                "session_id": session_id,
                "pair_count": len(sorted_items),
                "latest_time": sorted_items[0].time_label if sorted_items else "",
                "latest_timestamp": sorted_items[0].timestamp if sorted_items else "",
                "entries": [
                    {
                        "entry_id": item.entry_id,
                        "question": item.question,
                        "answer": item.answer,
                        "preview": item.preview,
                        "time_label": item.time_label,
                        "is_approved": item.is_approved,
                    }
                    for item in sorted_items[:limit_per_session]
                ],
            }
        )

    session_groups.sort(key=lambda item: item["latest_timestamp"], reverse=True)
    return session_groups


def _search_vector_entries(entries: list[VectorKnowledgeEntry], query: str, limit: int) -> list[dict]:
    return search_vector_entries_from_pipeline(
        entries,
        query,
        limit=limit,
        score_text_match_fn=_score_text_match,
        build_match_snippet_fn=_build_match_snippet,
        max_vector_snippet_chars=MAX_VECTOR_SNIPPET_CHARS,
    )
    results: list[dict] = []
    for entry in entries:
        score = _score_text_match(
            query,
            title=entry.display_name,
            body=f"{' '.join(entry.titles)}\n{entry.content}",
            source=entry.source,
        )
        if score <= 0:
            continue

        results.append(
            {
                "kind": "vector",
                "score": score,
                "title": entry.display_name,
                "subtitle": entry.tool_label,
                "source": entry.source,
                "meta": f"{entry.chunk_count} chunks",
                "snippet": _build_match_snippet(entry.content, query, MAX_VECTOR_SNIPPET_CHARS),
            }
        )

    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:limit]


def _search_chat_entries(entries: list[ChatKnowledgeEntry], query: str, limit: int) -> list[dict]:
    return search_chat_entries_from_pipeline(
        entries,
        query,
        limit=limit,
        score_text_match_fn=_score_text_match,
        build_match_snippet_fn=_build_match_snippet,
        max_chat_snippet_chars=MAX_CHAT_SNIPPET_CHARS,
    )
    results: list[dict] = []
    for entry in entries:
        score = _score_text_match(
            query,
            title=entry.question,
            body=entry.content,
            source=entry.session_id,
        )
        if score <= 0:
            continue

        results.append(
            {
                "kind": "chatbot",
                "score": score,
                "title": entry.question,
                "subtitle": f"Session {entry.session_id}",
                "source": entry.entry_id,
                "meta": entry.time_label,
                "snippet": _build_match_snippet(entry.answer, query, MAX_CHAT_SNIPPET_CHARS),
            }
        )

    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:limit]


def get_knowledge_base_payload(query: str = "", limit: int = 18) -> dict:
    vector_warning = ""
    chat_warning = ""
    search_scope_warning = ""

    try:
        vector_entries, total_chunks = _load_vector_entries()
    except Exception as exc:
        vector_entries, total_chunks = [], 0
        vector_warning = f"Vector store tạm thời chưa đọc được: {exc}"

    try:
        chat_entries = _load_chat_entries()
    except Exception as exc:
        chat_entries = []
        chat_warning = f"Chat history tạm thời chưa đọc được: {exc}"

    try:
        approved_chat_entries = get_approved_chat_qas()
    except Exception as exc:
        approved_chat_entries = []
        if not chat_warning:
            chat_warning = f"Không đọc được danh sách Q&A đã duyệt: {exc}"
    cleaned_query = query.strip()

    vector_results: list[dict] = []
    chat_results: list[dict] = []
    merged_results: list[dict] = []

    if cleaned_query and not is_ictu_related_query(cleaned_query):
        search_scope_warning = ICTU_SCOPE_REPLY_VI
    elif cleaned_query:
        vector_results = _search_vector_entries(vector_entries, cleaned_query, limit=limit)
        chat_results = _search_chat_entries(chat_entries, cleaned_query, limit=limit)
        merged_results = sorted(vector_results + chat_results, key=lambda item: item["score"], reverse=True)[:limit]

    recent_chat_entries = [
        {
            "entry_id": item.entry_id,
            "session_id": item.session_id,
            "question": item.question,
            "answer": item.answer,
            "preview": item.preview,
            "time_label": item.time_label,
            "is_approved": item.is_approved,
        }
        for item in chat_entries[:10]
    ]

    return {
        "query": cleaned_query,
        "approved_tool_name": DEFAULT_RAG_TOOL,
        "summary": {
            "vector_files": len(vector_entries),
            "vector_chunks": total_chunks,
            "chat_pairs": len(chat_entries),
            "approved_chat_qas": len(approved_chat_entries),
            "total_knowledge_items": len(vector_entries) + len(chat_entries),
            "matched_results": len(merged_results),
        },
        "warnings": [warning for warning in (vector_warning, chat_warning, search_scope_warning) if warning],
        "vector_groups": _group_vector_entries(vector_entries),
        "chat_sessions": _group_chat_entries(chat_entries),
        "recent_chat_entries": recent_chat_entries,
        "approved_chat_entries": approved_chat_entries[:12],
        "vector_results": vector_results,
        "chat_results": chat_results,
        "search_results": merged_results,
    }


