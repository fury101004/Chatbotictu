from __future__ import annotations

from typing import Optional

from langchain_core.documents import Document

from config.rag_tools import FALLBACK_RAG_NODE
from models.chat import RAGResult, RetrievedChunk
from services.ictu_scope_service import ICTU_SCOPE_REPLY_VI
from services.langchain_retrievers import WebKnowledgeRetriever, WebSearchRetriever
from services.rag_corpus import _extract_relevant_snippet, _tokenize
from services.rag_types import CorpusDocument
from services.web_knowledge_service import search_trusted_web_knowledge
from services.web_search import search_web_ictu

_UNTITLED_SENTINELS = {"Khong co tieu de", "Không có tiêu đề"}
_EMPTY_CONTEXT_SENTINELS = {"Thong tin dang duoc cap nhat.", "Thông tin đang được cập nhật.", ""}


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
        source = str(metadata.get("source", "") or "")
        title = str(metadata.get("title", "") or "").strip()
        context_entry = str(metadata.get("context_entry", "") or "").strip()

        if source and source != "BOT_RULE":
            extra_sources = metadata.get("sources")
            if isinstance(extra_sources, list):
                sources.extend(str(item) for item in extra_sources if item)
            else:
                sources.append(source)

        if context_entry:
            context_parts.append(context_entry)
            continue

        text = chunk.document.strip().replace("\n", " ")[:2000]
        if title and title not in _UNTITLED_SENTINELS:
            context_parts.append(f"[{title}]\n{text}")
        else:
            context_parts.append(text)

    context_text = "\n\n".join(context_parts) if context_parts else "Thông tin đang được cập nhật."
    chunks_used = len(limited_chunks)

    return RAGResult(
        context_text=context_text,
        chunks=chunks,
        target_file=target_file,
        mode=mode,
        sources=list(dict.fromkeys(source for source in sources if source)),
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

    context_text = "\n\n".join(context_parts) if context_parts else "Thông tin đang được cập nhật."
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
    missing_local_context = local_text in _EMPTY_CONTEXT_SENTINELS
    if missing_local_context:
        context_text = web_result.context_text
    elif web_first:
        context_text = f"{web_result.context_text}\n\n{local_result.context_text}"
    else:
        context_text = f"{local_result.context_text}\n\n{web_result.context_text}"

    chunks = [*web_result.chunks, *local_result.chunks] if web_first else [*local_result.chunks, *web_result.chunks]
    sources = [*web_result.sources, *local_result.sources] if web_first else [*local_result.sources, *web_result.sources]

    return RAGResult(
        context_text=context_text,
        chunks=chunks,
        target_file=local_result.target_file,
        mode=f"{local_result.mode}+web_search",
        sources=list(dict.fromkeys(sources)),
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
        title = chunk.metadata.get("title", "").strip()
        text = chunk.document.strip().replace("\n", " ")[:2000]
        source = chunk.metadata.get("source", "")

        if source and source != "BOT_RULE":
            sources.append(source)

        if title and title not in _UNTITLED_SENTINELS:
            context_parts.append(f"[{title}]\n{text}")
        else:
            context_parts.append(text)

    context_text = "\n\n".join(context_parts) if context_parts else "Thông tin đang được cập nhật."
    return context_text, sources
