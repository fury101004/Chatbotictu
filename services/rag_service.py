from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional
import re

from config.rag_tools import DEFAULT_RAG_TOOL, FALLBACK_RAG_NODE, QA_ROOT, RAG_TOOL_ORDER, RAG_TOOL_PROFILES
from models.chat import RAGResult, RetrievedChunk
from services.vector_store_service import SESSION_MEMORY, get_collection, inject_bot_rule, query_documents


@dataclass(slots=True)
class CorpusDocument:
    path: Path
    source: str
    title: str
    text: str
    text_lower: str
    token_set: frozenset[str]



def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"\w+", text.casefold()) if len(token) > 1]


@lru_cache(maxsize=32)
def _load_tool_corpus(tool_name: str) -> tuple[CorpusDocument, ...]:
    profile = RAG_TOOL_PROFILES.get(tool_name, {})
    corpus_paths = profile.get("corpus_paths", [])
    documents: list[CorpusDocument] = []
    seen_paths: set[Path] = set()

    for raw_path in corpus_paths:
        path = Path(raw_path)
        if not path.exists():
            continue

        if path.is_file() and path.suffix.lower() == ".md":
            file_paths = [path]
        elif path == QA_ROOT:
            file_paths = sorted(candidate for candidate in path.glob("*.md") if candidate.is_file())
        else:
            file_paths = sorted(candidate for candidate in path.rglob("*.md") if candidate.is_file())

        for file_path in file_paths:
            if file_path in seen_paths:
                continue
            seen_paths.add(file_path)

            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            source = _relative_source(file_path)
            title = _extract_title(text, file_path)
            text_lower = text.casefold()
            token_set = frozenset(_tokenize(f"{title}\n{source}\n{text_lower}"))
            documents.append(
                CorpusDocument(
                    path=file_path,
                    source=source,
                    title=title,
                    text=text,
                    text_lower=text_lower,
                    token_set=token_set,
                )
            )

    return tuple(documents)


@lru_cache(maxsize=1)
def _load_all_tool_documents() -> tuple[CorpusDocument, ...]:
    documents: list[CorpusDocument] = []
    seen_sources: set[str] = set()
    for tool_name in RAG_TOOL_ORDER:
        for doc in _load_tool_corpus(tool_name):
            if doc.source in seen_sources:
                continue
            seen_sources.add(doc.source)
            documents.append(doc)
    return tuple(documents)



def _relative_source(path: Path) -> str:
    try:
        return path.relative_to(QA_ROOT).as_posix()
    except ValueError:
        return path.name



def _extract_title(text: str, file_path: Path) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
        if stripped.lower().startswith("title:"):
            return stripped.split(":", 1)[1].strip().strip('"')
    return file_path.stem



def _candidate_phrases(message: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", message.casefold()).strip()
    phrases: list[str] = []
    if normalized:
        phrases.append(normalized)

    tokens = _tokenize(normalized)
    if len(tokens) >= 2:
        phrases.extend(" ".join(tokens[i : i + 2]) for i in range(len(tokens) - 1))
    if len(tokens) >= 3:
        phrases.extend(" ".join(tokens[i : i + 3]) for i in range(len(tokens) - 2))
    return phrases[:8]



def _score_document(doc: CorpusDocument, query_tokens: list[str], query_phrases: list[str]) -> int:
    if not query_tokens:
        return 0

    unique_tokens = set(query_tokens)
    token_overlap = sum(1 for token in unique_tokens if token in doc.token_set)
    source_overlap = sum(1 for token in unique_tokens if token in doc.source.casefold())
    title_overlap = sum(1 for token in unique_tokens if token in doc.title.casefold())
    phrase_hits = sum(1 for phrase in query_phrases if len(phrase) >= 6 and phrase in doc.text_lower)
    qa_bonus = 2 if "**q:**" in doc.text_lower and token_overlap >= 2 else 0

    return token_overlap * 4 + source_overlap * 3 + title_overlap * 2 + phrase_hits * 5 + qa_bonus



def _extract_relevant_snippet(doc: CorpusDocument, query_tokens: list[str], max_chars: int = 2200) -> str:
    lines = [line.strip() for line in doc.text.splitlines() if line.strip()]
    if not lines:
        return doc.text[:max_chars]

    matched_lines = [line for line in lines if any(token in line.casefold() for token in query_tokens)]
    selected_lines = matched_lines[:10] if matched_lines else lines[:12]

    snippet = "\n".join(selected_lines).strip()
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars].rstrip()
    return snippet



def _build_result_from_matches(
    *,
    message: str,
    matches: list[tuple[int, CorpusDocument]],
    tool_name: str,
    route_name: str,
    mode: str,
) -> RAGResult:
    query_tokens = _tokenize(message)
    context_parts: list[str] = []
    sources: list[str] = []
    chunks: list[RetrievedChunk] = []

    for score, doc in matches:
        snippet = _extract_relevant_snippet(doc, query_tokens)
        context_parts.append(f"[{doc.title} | source: {doc.source} | score: {score}]\n{snippet}")
        sources.append(doc.source)
        chunks.append(
            RetrievedChunk(
                document=snippet,
                metadata={
                    "source": doc.source,
                    "title": doc.title,
                    "score": score,
                    "tool_name": tool_name,
                    "path": str(doc.path),
                },
            )
        )

    context_text = "\n\n".join(context_parts) if context_parts else "Thong tin dang duoc cap nhat."
    return RAGResult(
        context_text=context_text,
        chunks=chunks,
        target_file=None,
        mode=mode,
        sources=list(dict.fromkeys(sources)),
        chunks_used=len(chunks),
        rag_tool=tool_name,
        rag_route=route_name,
    )



def _search_documents(documents: tuple[CorpusDocument, ...], message: str, limit: int = 4) -> list[tuple[int, CorpusDocument]]:
    query_tokens = _tokenize(message)
    query_phrases = _candidate_phrases(message)

    scored = [
        (score, doc)
        for doc in documents
        if (score := _score_document(doc, query_tokens, query_phrases)) > 0
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[:limit]



def route_rag_tool(message: str) -> tuple[str, str]:
    message_lower = message.casefold()
    scores: dict[str, int] = {}

    for tool_name, profile in RAG_TOOL_PROFILES.items():
        keywords = profile.get("route_keywords", [])
        score = sum(2 for keyword in keywords if keyword in message_lower)
        if tool_name == "student_faq_rag" and any(
            cue in message_lower for cue in ["khi nào", "khi nao", "bao giờ", "bao gio", "ở đâu", "o dau", "làm sao", "lam sao"]
        ):
            score += 2
        scores[tool_name] = score

    best_tool = max(scores, key=scores.get)
    best_score = scores[best_tool]

    if best_score <= 0:
        return FALLBACK_RAG_NODE, "router_fallback"

    return best_tool, f"router_keyword_score:{best_score}"



def retrieve_tool_context(message: str, session_id: str, tool_name: str, route_name: str) -> RAGResult:
    documents = _load_tool_corpus(tool_name)
    matches = _search_documents(documents, message, limit=4)

    if not matches:
        return retrieve_general_context(message, session_id, route_name=route_name, tool_name=tool_name)

    inject_bot_rule(force_full=True)
    return _build_result_from_matches(
        message=message,
        matches=matches,
        tool_name=tool_name,
        route_name=route_name,
        mode=tool_name,
    )



def retrieve_fallback_context(message: str, session_id: str, route_name: str = "router_fallback") -> RAGResult:
    all_matches: list[tuple[int, CorpusDocument]] = []
    for tool_name in RAG_TOOL_ORDER:
        documents = _load_tool_corpus(tool_name)
        all_matches.extend(_search_documents(documents, message, limit=2))

    all_matches.sort(key=lambda item: item[0], reverse=True)
    top_matches = all_matches[:6]

    if not top_matches:
        return retrieve_general_context(message, session_id, route_name=route_name, tool_name=DEFAULT_RAG_TOOL)

    inject_bot_rule(force_full=True)
    return _build_result_from_matches(
        message=message,
        matches=top_matches,
        tool_name=FALLBACK_RAG_NODE,
        route_name=route_name,
        mode="multi_tool_fallback_rag",
    )



def detect_target_file(message_lower: str, documents: Optional[tuple[CorpusDocument, ...]] = None) -> Optional[str]:
    pool = documents if documents is not None else _load_all_tool_documents()
    for doc in pool:
        name = doc.path.stem.casefold()
        variants = [name, name.replace("-", " "), doc.source.casefold()]
        if any(variant in message_lower for variant in variants if len(variant) > 2):
            return doc.source
    return None



def _detect_collection_source(message_lower: str) -> Optional[str]:
    try:
        coll = get_collection()
        data = coll.get(include=["metadatas"])
    except Exception as exc:
        print(f"Vector source detection unavailable: {exc}")
        return None

    all_sources = {m.get("source", "") for m in data.get("metadatas", []) if m}

    for src in all_sources:
        if src == "BOT_RULE":
            continue
        name = src.lower().replace(".md", "").replace(".markdown", "")
        variants = [name, name.replace("-", " "), f"file {name}", f"trong {name}"]
        if any(variant in message_lower for variant in variants if len(variant) > 2):
            return src
    return None



def build_retrieval_query(session_id: str, message: str) -> str:
    history = SESSION_MEMORY[session_id]
    if history:
        previous_q = history[-1]["query"]
        return f"{previous_q} {message}"
    return message



def build_context_from_chunks(chunks: list[RetrievedChunk], max_chunks: int = 25) -> tuple[str, list[str]]:
    context_parts: list[str] = []
    sources: list[str] = []

    for chunk in chunks[:max_chunks]:
        title = chunk.metadata.get("title", "").strip()
        text = chunk.document.strip().replace("\n", " ")[:2000]
        source = chunk.metadata.get("source", "")

        if source and source != "BOT_RULE":
            sources.append(source)

        if title and title != "Khong co tieu de":
            context_parts.append(f"[{title}]\n{text}")
        else:
            context_parts.append(text)

    context_text = "\n\n".join(context_parts) if context_parts else "Thong tin dang duoc cap nhat."
    return context_text, sources



def _build_general_fallback_result(message: str, route_name: str, tool_name: Optional[str]) -> RAGResult:
    matches = _search_documents(_load_all_tool_documents(), message, limit=6)
    if matches:
        return _build_result_from_matches(
            message=message,
            matches=matches,
            tool_name=tool_name or FALLBACK_RAG_NODE,
            route_name=route_name,
            mode="lexical_fallback",
        )

    return RAGResult(
        context_text="Thong tin dang duoc cap nhat.",
        chunks=[],
        target_file=None,
        mode="lexical_fallback_empty",
        sources=[],
        chunks_used=0,
        rag_tool=tool_name,
        rag_route=route_name,
    )



def retrieve_general_context(message: str, session_id: str, route_name: str = "general_fallback", tool_name: Optional[str] = None) -> RAGResult:
    message_lower = message.lower()
    query_for_retrieval = build_retrieval_query(session_id, message)
    target_file = None

    try:
        target_file = _detect_collection_source(message_lower)
        coll = get_collection()

        if target_file:
            data = coll.get(where={"source": target_file}, include=["documents", "metadatas"])
            chunks = [
                RetrievedChunk(document=doc, metadata=meta)
                for doc, meta in zip(data.get("documents", []), data.get("metadatas", []))
            ]
            mode = "forced_file"
        else:
            docs, metas, _ = query_documents(query_for_retrieval, user_id=session_id, n_results=100, alpha=0.7)
            chunks = [RetrievedChunk(document=doc, metadata=meta) for doc, meta in zip(docs, metas)]
            mode = "hybrid_search"
    except Exception as exc:
        print(f"Vector retrieval unavailable, using lexical fallback: {exc}")
        return _build_general_fallback_result(message, route_name, tool_name)

    context_text, sources = build_context_from_chunks(chunks)
    inject_bot_rule(force_full=True)

    unique_sources = list(dict.fromkeys(source for source in sources if source))
    return RAGResult(
        context_text=context_text,
        chunks=chunks,
        target_file=target_file,
        mode=mode,
        sources=unique_sources,
        chunks_used=min(len(chunks), 25),
        rag_tool=tool_name,
        rag_route=route_name,
    )



def retrieve_context(message: str, session_id: str) -> RAGResult:
    return retrieve_general_context(message, session_id)






