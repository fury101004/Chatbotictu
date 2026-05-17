from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Optional
import re

from config.rag_tools import (
    DEFAULT_RAG_TOOL,
    RAG_TOOL_ORDER,
    RAG_TOOL_PROFILES,
    UPLOAD_SOURCE_PREFIX,
    get_tool_upload_dir,
    is_valid_rag_tool,
)
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
    list_chat_qa_review_states,
    save_approved_chat_qa,
    save_chat_qa_review_state,
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
    review_status: str = "unreviewed"
    review_reason: str = ""
    is_reviewable: bool = False


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


def _load_chat_entries() -> list[ChatKnowledgeEntry]:
    try:
        approved_entry_ids = get_approved_chat_entry_ids()
    except Exception:
        approved_entry_ids = set()
    try:
        review_states = list_chat_qa_review_states()
    except Exception:
        review_states = {}
    entries = _pair_chat_rows(_fetch_chat_rows())
    for entry in entries:
        state = review_states.get(entry.entry_id, {})
        status = str(state.get("status") or "unreviewed")
        entry.is_approved = entry.entry_id in approved_entry_ids or status == "approved"
        entry.review_status = "approved" if entry.is_approved else status
        entry.review_reason = str(state.get("reason") or "")
        entry.is_reviewable = entry.review_status in {"pending", "unreviewed"}
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


def approve_chat_entry(entry_id: str, tool_name: str = DEFAULT_RAG_TOOL) -> dict:
    entry = get_chat_entry_by_id(entry_id)
    if entry is None:
        raise ValueError("Khong tim thay cap hoi dap chatbot de duyet.")

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
    save_chat_qa_review_state(
        entry_id=entry.entry_id,
        status="approved",
        tool_name=selected_tool,
        reason="",
        reviewer="admin",
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
            warning = f"Saved approved Q&A but vector indexing failed: {exc}"
    else:
        warning = "Saved approved Q&A, but embedding backend is not ready for indexing."

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
            "Approved Q&A into knowledge base and indexed vector store."
            if indexed
            else "Approved Q&A into knowledge base."
        ),
    }


def mark_chat_entry_pending(entry_id: str, tool_name: str = DEFAULT_RAG_TOOL, reason: str = "") -> None:
    selected_tool = tool_name if is_valid_rag_tool(tool_name) else DEFAULT_RAG_TOOL
    save_chat_qa_review_state(
        entry_id=entry_id,
        status="pending",
        tool_name=selected_tool,
        reason=reason,
        reviewer="system",
    )


def reject_chat_entry(entry_id: str, reason: str = "", reviewer: str = "admin") -> dict:
    entry = get_chat_entry_by_id(entry_id)
    if entry is None:
        raise ValueError("Khong tim thay cap hoi dap chatbot de tu choi.")

    save_chat_qa_review_state(
        entry_id=entry.entry_id,
        status="rejected",
        tool_name="",
        reason=reason,
        reviewer=reviewer,
    )
    clear_rag_corpus_cache()
    return {
        "entry_id": entry.entry_id,
        "status": "rejected",
        "message": "Da tu choi Q&A, khong index vao Knowledge Base.",
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


def _group_vector_entries(entries: list[VectorKnowledgeEntry], limit_per_tool: int = 8) -> list[dict]:
    return group_vector_entries_from_pipeline(
        entries,
        rag_tool_order=RAG_TOOL_ORDER,
        rag_tool_profiles=RAG_TOOL_PROFILES,
        limit_per_tool=limit_per_tool,
    )


def _group_chat_entries(entries: list[ChatKnowledgeEntry], limit_per_session: int = 6) -> list[dict]:
    return group_chat_entries_from_pipeline(entries, limit_per_session=limit_per_session)


def _search_vector_entries(entries: list[VectorKnowledgeEntry], query: str, limit: int) -> list[dict]:
    return search_vector_entries_from_pipeline(
        entries,
        query,
        limit=limit,
        score_text_match_fn=_score_text_match,
        build_match_snippet_fn=_build_match_snippet,
        max_vector_snippet_chars=MAX_VECTOR_SNIPPET_CHARS,
    )


def _search_chat_entries(entries: list[ChatKnowledgeEntry], query: str, limit: int) -> list[dict]:
    return search_chat_entries_from_pipeline(
        entries,
        query,
        limit=limit,
        score_text_match_fn=_score_text_match,
        build_match_snippet_fn=_build_match_snippet,
        max_chat_snippet_chars=MAX_CHAT_SNIPPET_CHARS,
    )


def get_knowledge_base_payload(query: str = "", limit: int = 18) -> dict:
    vector_warning = ""
    chat_warning = ""
    search_scope_warning = ""

    try:
        vector_entries, total_chunks = _load_vector_entries()
    except Exception as exc:
        vector_entries, total_chunks = [], 0
        vector_warning = f"Vector store is temporarily unavailable: {exc}"

    try:
        chat_entries = _load_chat_entries()
    except Exception as exc:
        chat_entries = []
        chat_warning = f"Chat history is temporarily unavailable: {exc}"

    try:
        approved_chat_entries = get_approved_chat_qas()
    except Exception as exc:
        approved_chat_entries = []
        if not chat_warning:
            chat_warning = f"Approved Q&A list is temporarily unavailable: {exc}"
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
            "review_status": item.review_status,
            "review_reason": item.review_reason,
            "is_reviewable": item.is_reviewable,
        }
        for item in chat_entries[:10]
    ]
    pending_chat_qas = sum(1 for item in chat_entries if item.review_status == "pending")
    rejected_chat_qas = sum(1 for item in chat_entries if item.review_status == "rejected")

    return {
        "query": cleaned_query,
        "approved_tool_name": DEFAULT_RAG_TOOL,
        "summary": {
            "vector_files": len(vector_entries),
            "vector_chunks": total_chunks,
            "chat_pairs": len(chat_entries),
            "approved_chat_qas": len(approved_chat_entries),
            "pending_chat_qas": pending_chat_qas,
            "rejected_chat_qas": rejected_chat_qas,
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
