from __future__ import annotations

from typing import Optional

from langchain_core.documents import Document

from config.rag_tools import FALLBACK_RAG_NODE
from models.chat import RAGResult, RetrievedChunk
from services.rag.citation_service import merge_sources, sources_from_metadata
from services.rag.context_builder import DEFAULT_CONTEXT_TEXT, build_context_entry, build_context_text
from services.rag.ictu_scope_service import ICTU_SCOPE_REPLY_VI, normalize_scope_text
from services.rag.langchain_retrievers import WebKnowledgeRetriever, WebSearchRetriever
from services.rag.rag_corpus import _extract_relevant_snippet, _tokenize
from services.rag.rag_types import CorpusDocument
from services.content.web_knowledge_service import search_trusted_web_knowledge
from services.content.web_search import search_web_ictu


_EMPTY_CONTEXT_SENTINELS = (DEFAULT_CONTEXT_TEXT, "")
_NORMALIZED_EMPTY_CONTEXT_SENTINELS = tuple(normalize_scope_text(marker) for marker in _EMPTY_CONTEXT_SENTINELS)


def _documents_to_chunks(documents: list[Document]) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            document=document.page_content,
            metadata=dict(document.metadata or {}),
        )
        for document in documents
    ]


def _build_result_from_documents(
    *,
    documents: list[Document],
    tool_name: Optional[str],
    route_name: str,
    mode: str,
    target_file: Optional[str] = None,
    context_max_chunks: Optional[int] = None,
) -> RAGResult:
    chunks = _documents_to_chunks(documents)
    limited_chunks = chunks[:context_max_chunks] if context_max_chunks is not None else chunks

    context_parts: list[str] = []
    sources: list[str] = []

    for chunk in limited_chunks:
        metadata = chunk.metadata
        title = str(metadata.get("title", "") or "").strip()
        context_entry = str(metadata.get("context_entry", "") or "").strip()

        sources = merge_sources(sources, sources_from_metadata(metadata))
        context_parts.append(
            build_context_entry(
                title=title,
                text=chunk.document,
                context_entry=context_entry,
            )
        )

    context_text = build_context_text(context_parts)
    chunks_used = len(limited_chunks)

    return RAGResult(
        context_text=context_text,
        chunks=chunks,
        target_file=target_file,
        mode=mode,
        sources=sources,
        chunks_used=chunks_used,
        rag_tool=tool_name,
        rag_route=route_name,
    )


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
        snippet = _extract_relevant_snippet(doc, message, query_tokens)
        context_parts.append(f"[{doc.title} | source: {doc.source} | score: {score}]\n{snippet}")
        sources = merge_sources(sources, [doc.source])
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

    context_text = build_context_text(context_parts)
    return RAGResult(
        context_text=context_text,
        chunks=chunks,
        target_file=None,
        mode=mode,
        sources=sources,
        chunks_used=len(chunks),
        rag_tool=tool_name,
        rag_route=route_name,
    )


def _build_web_search_result(message: str, route_name: str, tool_name: Optional[str]) -> Optional[RAGResult]:
    documents = WebSearchRetriever(
        search_fn=search_web_ictu,
        tool_name=tool_name or FALLBACK_RAG_NODE,
    ).invoke(message)
    if not documents:
        return None

    return _build_result_from_documents(
        documents=documents,
        tool_name=tool_name,
        route_name=route_name,
        mode="web_search",
    )


def _merge_web_search_result(local_result: RAGResult, web_result: Optional[RAGResult], *, web_first: bool = True) -> RAGResult:
    if web_result is None or not web_result.chunks:
        return local_result

    local_text = local_result.context_text.strip()
    missing_local_context = normalize_scope_text(local_text) in _NORMALIZED_EMPTY_CONTEXT_SENTINELS
    if missing_local_context:
        context_text = web_result.context_text
    elif web_first:
        context_text = f"{web_result.context_text}\n\n{local_result.context_text}"
    else:
        context_text = f"{local_result.context_text}\n\n{web_result.context_text}"

    chunks = [*web_result.chunks, *local_result.chunks] if web_first else [*local_result.chunks, *web_result.chunks]
    sources = merge_sources(web_result.sources, local_result.sources) if web_first else merge_sources(local_result.sources, web_result.sources)

    return RAGResult(
        context_text=context_text,
        chunks=chunks,
        target_file=local_result.target_file,
        mode=f"{local_result.mode}+web_search",
        sources=sources,
        chunks_used=local_result.chunks_used + web_result.chunks_used,
        rag_tool=local_result.rag_tool,
        rag_route=local_result.rag_route,
    )


def _build_web_knowledge_result(message: str, route_name: str, tool_name: Optional[str]) -> Optional[RAGResult]:
    documents = WebKnowledgeRetriever(
        search_fn=search_trusted_web_knowledge,
        tool_name=tool_name or FALLBACK_RAG_NODE,
    ).invoke(message)
    if not documents:
        return None

    return _build_result_from_documents(
        documents=documents,
        tool_name=tool_name,
        route_name=route_name,
        mode="web_knowledge_base",
    )


def _build_scope_guard_result(route_name: str, tool_name: Optional[str]) -> RAGResult:
    return RAGResult(
        context_text=ICTU_SCOPE_REPLY_VI,
        chunks=[],
        target_file=None,
        mode="ictu_scope_guard",
        sources=[],
        chunks_used=0,
        rag_tool=tool_name,
        rag_route=route_name,
    )


def build_context_from_chunks(chunks: list[RetrievedChunk], max_chunks: int = 25) -> tuple[str, list[str]]:
    context_parts: list[str] = []
    sources: list[str] = []

    for chunk in chunks[:max_chunks]:
        metadata = dict(chunk.metadata or {})
        title = str(metadata.get("title", "") or "").strip()
        context_parts.append(build_context_entry(title=title, text=chunk.document))
        sources = merge_sources(sources, sources_from_metadata(metadata))

    context_text = build_context_text(context_parts)
    return context_text, sources

