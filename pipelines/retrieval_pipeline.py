from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from models.chat import RAGResult
from services.rag_types import (
    RETRIEVAL_HYBRID,
    RETRIEVAL_WEB_FIRST,
    RETRIEVAL_WEB_SEARCH,
    CorpusDocument,
    RetrievalFlowPlan,
)


TOOL_LEXICAL_RETRIEVAL_LIMIT = 8
FALLBACK_LEXICAL_RETRIEVAL_LIMIT = 8


@dataclass(slots=True)
class RetrievalRuntime:
    is_ictu_related_query: Callable[[str], bool]
    route_retrieval_flow: Callable[[str, Optional[str]], RetrievalFlowPlan]
    build_scope_guard_result: Callable[[str, Optional[str]], RAGResult]
    build_planned_web_result: Callable[[str, str, Optional[str]], Optional[RAGResult]]
    merge_web_search_result: Callable[..., RAGResult]
    build_result_from_documents: Callable[..., RAGResult]
    corpus_lexical_retriever_cls: Any
    vector_store_retriever_cls: Any
    load_tool_corpus: Callable[[str], tuple[CorpusDocument, ...]]
    load_all_tool_documents: Callable[[], tuple[CorpusDocument, ...]]
    search_documents: Callable[..., list[tuple[int, CorpusDocument]]]
    extract_relevant_snippet: Callable[[CorpusDocument, str, list[str]], str]
    inject_bot_rule: Callable[..., None]
    embedding_backend_ready: Callable[[], bool]
    session_memory: Any
    history_loader: Callable[[str], list[dict[str, Any]]]
    list_vector_sources: Callable[[], set[str]]
    fetch_documents_by_source: Callable[[str], tuple[list[str], list[dict[str, Any]]]]
    search_vector_documents: Callable[..., tuple[list[str], list[dict[str, Any]], dict[str, Any]]]
    default_rag_tool: str
    fallback_rag_node: str
    rag_tool_order: tuple[str, ...]


def _plan_allows_web(plan: RetrievalFlowPlan) -> bool:
    return plan.source in {RETRIEVAL_WEB_SEARCH, RETRIEVAL_HYBRID}


def _plan_is_web_first(plan: RetrievalFlowPlan) -> bool:
    return plan.priority == RETRIEVAL_WEB_FIRST or plan.source == RETRIEVAL_WEB_SEARCH


def _detect_collection_source(message_lower: str, runtime: RetrievalRuntime) -> Optional[str]:
    all_sources = runtime.list_vector_sources()
    for source in all_sources:
        if source == "BOT_RULE":
            continue
        name = source.lower().replace(".md", "").replace(".markdown", "")
        variants = [name, name.replace("-", " "), f"file {name}", f"trong {name}"]
        if any(variant in message_lower for variant in variants if len(variant) > 2):
            return source
    return None


def _normalize_message_key(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().casefold()


def _get_previous_user_message_from_db(runtime: RetrievalRuntime, session_id: str, current_message: str) -> str:
    try:
        history = runtime.history_loader(session_id)
    except Exception:
        return ""

    user_messages = [
        str(item.get("content") or "").strip()
        for item in history
        if str(item.get("role") or "").strip().casefold() == "user"
    ]
    if not user_messages:
        return ""

    current_key = _normalize_message_key(current_message)
    for candidate in reversed(user_messages):
        normalized_candidate = _normalize_message_key(candidate)
        if normalized_candidate and normalized_candidate != current_key:
            return candidate
    return ""


def build_retrieval_query(runtime: RetrievalRuntime, session_id: str, message: str) -> str:
    current_message = str(message or "").strip()
    if not current_message:
        return ""

    previous_q = ""
    history = runtime.session_memory.get(session_id)
    if history:
        previous_q = str(history[-1].get("query") or "").strip()
    if not previous_q:
        previous_q = _get_previous_user_message_from_db(runtime, session_id, current_message)

    if not previous_q:
        return current_message
    if _normalize_message_key(previous_q) == _normalize_message_key(current_message):
        return current_message
    return f"{previous_q} {current_message}"


def _build_general_fallback_result(
    runtime: RetrievalRuntime,
    *,
    message: str,
    route_name: str,
    tool_name: Optional[str],
    retrieval_plan: Optional[RetrievalFlowPlan] = None,
) -> RAGResult:
    flow_plan = retrieval_plan or runtime.route_retrieval_flow(message, tool_name)
    web_result: Optional[RAGResult] = None

    if _plan_allows_web(flow_plan) and _plan_is_web_first(flow_plan):
        web_result = runtime.build_planned_web_result(message, route_name, tool_name)
        if web_result is not None and flow_plan.source == RETRIEVAL_WEB_SEARCH:
            return web_result

    fallback_documents = runtime.corpus_lexical_retriever_cls(
        document_supplier=runtime.load_all_tool_documents,
        search_fn=runtime.search_documents,
        snippet_fn=runtime.extract_relevant_snippet,
        tool_name=tool_name or runtime.fallback_rag_node,
        limit=FALLBACK_LEXICAL_RETRIEVAL_LIMIT,
    ).invoke(message)
    if fallback_documents:
        result = runtime.build_result_from_documents(
            documents=fallback_documents,
            tool_name=tool_name or runtime.fallback_rag_node,
            route_name=route_name,
            mode="lexical_fallback",
        )

        if flow_plan.source == RETRIEVAL_WEB_SEARCH:
            web_result = web_result or runtime.build_planned_web_result(message, route_name, tool_name)
            return web_result or result

        if flow_plan.source == RETRIEVAL_HYBRID:
            web_result = web_result or runtime.build_planned_web_result(message, route_name, tool_name)
            return runtime.merge_web_search_result(
                result,
                web_result,
                web_first=_plan_is_web_first(flow_plan),
            )

        return result

    result = RAGResult(
        context_text="ThĂ´ng tin Ä‘ang Ä‘Æ°á»£c cáº­p nháº­t.",
        chunks=[],
        target_file=None,
        mode="lexical_fallback_empty",
        sources=[],
        chunks_used=0,
        rag_tool=tool_name,
        rag_route=route_name,
    )

    if _plan_allows_web(flow_plan):
        return runtime.merge_web_search_result(
            result,
            web_result or runtime.build_planned_web_result(message, route_name, tool_name),
            web_first=_plan_is_web_first(flow_plan),
        )
    return result


def retrieve_tool_context(
    runtime: RetrievalRuntime,
    *,
    message: str,
    session_id: str,
    tool_name: str,
    route_name: str,
    retrieval_plan: Optional[RetrievalFlowPlan] = None,
) -> RAGResult:
    scope_query = build_retrieval_query(runtime, session_id, message)
    if not runtime.is_ictu_related_query(scope_query):
        return runtime.build_scope_guard_result(route_name=route_name, tool_name=tool_name)

    flow_plan = retrieval_plan or runtime.route_retrieval_flow(scope_query, tool_name)
    planned_route_name = f"{route_name}|{flow_plan.route}"
    web_result: Optional[RAGResult] = None

    if _plan_allows_web(flow_plan) and _plan_is_web_first(flow_plan):
        web_result = runtime.build_planned_web_result(scope_query, planned_route_name, tool_name)
        if web_result is not None and flow_plan.source == RETRIEVAL_WEB_SEARCH:
            return web_result

    lexical_documents = runtime.corpus_lexical_retriever_cls(
        document_supplier=lambda: runtime.load_tool_corpus(tool_name),
        search_fn=runtime.search_documents,
        snippet_fn=runtime.extract_relevant_snippet,
        tool_name=tool_name,
        limit=TOOL_LEXICAL_RETRIEVAL_LIMIT,
    ).invoke(message)

    if not lexical_documents:
        if web_result is not None:
            return web_result
        if _plan_allows_web(flow_plan):
            web_result = runtime.build_planned_web_result(scope_query, planned_route_name, tool_name)
            if web_result is not None:
                return web_result
        return retrieve_general_context(
            runtime,
            message=message,
            session_id=session_id,
            route_name=planned_route_name,
            tool_name=tool_name,
            retrieval_plan=flow_plan,
        )

    runtime.inject_bot_rule(force_full=True)
    result = runtime.build_result_from_documents(
        documents=lexical_documents,
        tool_name=tool_name,
        route_name=planned_route_name,
        mode=tool_name,
    )

    if flow_plan.source == RETRIEVAL_WEB_SEARCH:
        web_result = web_result or runtime.build_planned_web_result(scope_query, planned_route_name, tool_name)
        return web_result or result

    if flow_plan.source == RETRIEVAL_HYBRID:
        web_result = web_result or runtime.build_planned_web_result(scope_query, planned_route_name, tool_name)
        return runtime.merge_web_search_result(
            result,
            web_result,
            web_first=_plan_is_web_first(flow_plan),
        )

    return result


def retrieve_fallback_context(
    runtime: RetrievalRuntime,
    *,
    message: str,
    session_id: str,
    route_name: str = "router_fallback",
    retrieval_plan: Optional[RetrievalFlowPlan] = None,
) -> RAGResult:
    scope_query = build_retrieval_query(runtime, session_id, message)
    if not runtime.is_ictu_related_query(scope_query):
        return runtime.build_scope_guard_result(route_name=route_name, tool_name=runtime.fallback_rag_node)

    flow_plan = retrieval_plan or runtime.route_retrieval_flow(scope_query, runtime.fallback_rag_node)
    planned_route_name = f"{route_name}|{flow_plan.route}"
    web_result: Optional[RAGResult] = None

    if _plan_allows_web(flow_plan) and _plan_is_web_first(flow_plan):
        web_result = runtime.build_planned_web_result(scope_query, planned_route_name, runtime.fallback_rag_node)
        if web_result is not None and flow_plan.source == RETRIEVAL_WEB_SEARCH:
            return web_result

    def _fallback_search(_: tuple[CorpusDocument, ...], query: str, limit: int = 6) -> list[tuple[int, CorpusDocument]]:
        all_matches: list[tuple[int, CorpusDocument]] = []
        for tool in runtime.rag_tool_order:
            documents = runtime.load_tool_corpus(tool)
            all_matches.extend(runtime.search_documents(documents, query, limit=2))
        all_matches.sort(key=lambda item: item[0], reverse=True)
        return all_matches[:limit]

    fallback_documents = runtime.corpus_lexical_retriever_cls(
        document_supplier=runtime.load_all_tool_documents,
        search_fn=_fallback_search,
        snippet_fn=runtime.extract_relevant_snippet,
        tool_name=runtime.fallback_rag_node,
        limit=FALLBACK_LEXICAL_RETRIEVAL_LIMIT,
    ).invoke(message)

    if not fallback_documents:
        if web_result is not None:
            return web_result
        if _plan_allows_web(flow_plan):
            web_result = runtime.build_planned_web_result(scope_query, planned_route_name, runtime.fallback_rag_node)
            if web_result is not None:
                return web_result
        return retrieve_general_context(
            runtime,
            message=message,
            session_id=session_id,
            route_name=planned_route_name,
            tool_name=runtime.default_rag_tool,
            retrieval_plan=flow_plan,
        )

    runtime.inject_bot_rule(force_full=True)
    result = runtime.build_result_from_documents(
        documents=fallback_documents,
        tool_name=runtime.fallback_rag_node,
        route_name=planned_route_name,
        mode="multi_tool_fallback_rag",
    )

    if flow_plan.source == RETRIEVAL_WEB_SEARCH:
        web_result = web_result or runtime.build_planned_web_result(
            scope_query,
            planned_route_name,
            runtime.fallback_rag_node,
        )
        return web_result or result

    if flow_plan.source == RETRIEVAL_HYBRID:
        web_result = web_result or runtime.build_planned_web_result(
            scope_query,
            planned_route_name,
            runtime.fallback_rag_node,
        )
        return runtime.merge_web_search_result(
            result,
            web_result,
            web_first=_plan_is_web_first(flow_plan),
        )

    return result


def retrieve_general_context(
    runtime: RetrievalRuntime,
    *,
    message: str,
    session_id: str,
    route_name: str = "general_fallback",
    tool_name: Optional[str] = None,
    retrieval_plan: Optional[RetrievalFlowPlan] = None,
) -> RAGResult:
    query_for_retrieval = build_retrieval_query(runtime, session_id, message)
    if not runtime.is_ictu_related_query(query_for_retrieval):
        return runtime.build_scope_guard_result(route_name=route_name, tool_name=tool_name)

    flow_plan = retrieval_plan or runtime.route_retrieval_flow(query_for_retrieval, tool_name)
    planned_route_name = route_name if f"|{flow_plan.route}" in route_name else f"{route_name}|{flow_plan.route}"
    web_result: Optional[RAGResult] = None

    if _plan_allows_web(flow_plan) and _plan_is_web_first(flow_plan):
        web_result = runtime.build_planned_web_result(query_for_retrieval, planned_route_name, tool_name)
        if web_result is not None and flow_plan.source == RETRIEVAL_WEB_SEARCH:
            return web_result

    message_lower = message.lower()
    target_file = None

    if not runtime.embedding_backend_ready():
        return _build_general_fallback_result(
            runtime,
            message=message,
            route_name=planned_route_name,
            tool_name=tool_name,
            retrieval_plan=flow_plan,
        )

    try:
        target_file = _detect_collection_source(message_lower, runtime)
        documents = runtime.vector_store_retriever_cls(
            query_fn=runtime.search_vector_documents,
            collection_getter=None,
            source_lookup_fn=runtime.fetch_documents_by_source,
            user_id=session_id,
            n_results=100,
            alpha=0.7,
            target_source=target_file,
        ).invoke(query_for_retrieval)
        mode = "forced_file" if target_file else "hybrid_search"
    except Exception as exc:
        print(f"Vector retrieval unavailable, using lexical fallback: {exc}")
        return _build_general_fallback_result(
            runtime,
            message=message,
            route_name=planned_route_name,
            tool_name=tool_name,
            retrieval_plan=flow_plan,
        )

    runtime.inject_bot_rule(force_full=True)
    result = runtime.build_result_from_documents(
        documents=documents,
        tool_name=tool_name,
        route_name=planned_route_name,
        mode=mode,
        target_file=target_file,
        context_max_chunks=25,
    )
    unique_sources = result.sources

    if flow_plan.source == RETRIEVAL_WEB_SEARCH:
        web_result = web_result or runtime.build_planned_web_result(query_for_retrieval, planned_route_name, tool_name)
        return web_result or result

    if flow_plan.source == RETRIEVAL_HYBRID or (not unique_sources and _plan_allows_web(flow_plan)):
        web_result = web_result or runtime.build_planned_web_result(query_for_retrieval, planned_route_name, tool_name)
        return runtime.merge_web_search_result(
            result,
            web_result,
            web_first=_plan_is_web_first(flow_plan),
        )

    return result
