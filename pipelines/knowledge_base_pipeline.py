from __future__ import annotations

import re
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Callable


def display_timestamp(raw_timestamp: str) -> str:
    try:
        parsed = datetime.strptime(raw_timestamp.split(".")[0], "%Y-%m-%d %H:%M:%S")
        return parsed.strftime("%d/%m %H:%M")
    except Exception:
        return raw_timestamp or "Vua xong"


def pair_chat_rows(
    rows: list[dict[str, Any]],
    *,
    max_chat_snippet_chars: int,
    build_chat_entry_id: Callable[[str, int], str],
    entry_factory: Callable[..., Any],
) -> list[Any]:
    pending_question_by_session: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    pairs: list[Any] = []

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
        if len(preview) > max_chat_snippet_chars:
            preview = preview[:max_chat_snippet_chars].rstrip() + " ..."

        question_row_id = int(pending.get("id") or 0)
        answer_row_id = int(row.get("id") or 0)
        pairs.append(
            entry_factory(
                entry_id=build_chat_entry_id(session_id, answer_row_id),
                question_row_id=question_row_id,
                answer_row_id=answer_row_id,
                session_id=session_id,
                question=question,
                answer=answer,
                timestamp=timestamp,
                time_label=display_timestamp(timestamp),
                preview=preview,
                content=f"Q: {question}\nA: {answer}",
            )
        )

    pairs.sort(key=lambda item: (item.timestamp, item.entry_id), reverse=True)
    return pairs


def build_approved_chat_markdown(entry: Any, tool_name: str) -> str:
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
        "## Ghi chú",
        "",
        "- Nguồn này được tạo từ cặp hỏi đáp chatbot đã duyệt thủ công.",
        "- Có thể được đồng bộ vào vector store để dùng lại trong retrieval.",
        "",
    ]
    return "\n".join(lines)


def load_vector_entries(
    raw: dict[str, list[Any]],
    *,
    default_rag_tool: str,
    rag_tool_profiles: dict[str, dict[str, Any]],
    infer_vector_tool_name: Callable[[str, str | None], str | None],
    display_vector_source: Callable[[str], str],
    max_vector_content_chars: int,
    max_vector_snippet_chars: int,
    entry_factory: Callable[..., Any],
) -> tuple[list[Any], int]:
    grouped: dict[str, dict[str, Any]] = {}
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
                "tool_name": infer_vector_tool_name(source, (metadata or {}).get("tool_name")) or default_rag_tool,
                "titles": [],
                "documents": [],
            },
        )

        title = str((metadata or {}).get("title", "")).strip()
        if title:
            bucket["titles"].append(title)
        bucket["documents"].append(str(document or "").strip())

    entries: list[Any] = []
    for source, bucket in grouped.items():
        tool_name = str(bucket["tool_name"])
        tool_label = str(rag_tool_profiles.get(tool_name, {}).get("label", tool_name))
        combined_content = "\n\n".join(piece for piece in bucket["documents"] if piece).strip()
        if len(combined_content) > max_vector_content_chars:
            combined_content = combined_content[:max_vector_content_chars].rstrip() + " ..."

        preview = re.sub(r"\s+", " ", combined_content)
        if len(preview) > max_vector_snippet_chars:
            preview = preview[:max_vector_snippet_chars].rstrip() + " ..."

        unique_titles = list(dict.fromkeys(title for title in bucket["titles"] if title))
        entries.append(
            entry_factory(
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


def group_vector_entries(
    entries: list[Any],
    *,
    rag_tool_order: list[str],
    rag_tool_profiles: dict[str, dict[str, Any]],
    limit_per_tool: int = 8,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for entry in entries:
        grouped[entry.tool_name].append(entry)

    payload: list[dict[str, Any]] = []
    for tool_name in rag_tool_order:
        items = grouped.get(tool_name, [])
        profile = rag_tool_profiles.get(tool_name, {})
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


def group_chat_entries(entries: list[Any], *, limit_per_session: int = 6) -> list[dict[str, Any]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for entry in entries:
        grouped[entry.session_id].append(entry)

    session_groups: list[dict[str, Any]] = []
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


def search_vector_entries(
    entries: list[Any],
    query: str,
    *,
    limit: int,
    score_text_match_fn: Callable[..., int],
    build_match_snippet_fn: Callable[[str, str, int], str],
    max_vector_snippet_chars: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for entry in entries:
        score = score_text_match_fn(
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
                "snippet": build_match_snippet_fn(entry.content, query, max_vector_snippet_chars),
            }
        )
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:limit]


def search_chat_entries(
    entries: list[Any],
    query: str,
    *,
    limit: int,
    score_text_match_fn: Callable[..., int],
    build_match_snippet_fn: Callable[[str, str, int], str],
    max_chat_snippet_chars: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for entry in entries:
        score = score_text_match_fn(
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
                "snippet": build_match_snippet_fn(entry.answer, query, max_chat_snippet_chars),
            }
        )
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:limit]
