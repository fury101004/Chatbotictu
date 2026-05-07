from __future__ import annotations

from typing import Optional

from config.rag_tools import DEFAULT_RAG_TOOL, FALLBACK_RAG_NODE, RAG_TOOL_ORDER, RAG_TOOL_PROFILES
from models.chat import RAGResult
from pipelines.retrieval_pipeline import (
    RetrievalRuntime,
    build_retrieval_query as _build_retrieval_query_impl,
    extract_router_json as _extract_router_json_impl,
    fallback_retrieval_flow as _fallback_retrieval_flow_impl,
    keyword_route_score as _keyword_route_score_impl,
    normalize_retrieval_priority as _normalize_retrieval_priority_impl,
    normalize_retrieval_source as _normalize_retrieval_source_impl,
    retrieve_fallback_context as _retrieve_fallback_context_impl,
    retrieve_general_context as _retrieve_general_context_impl,
    retrieve_tool_context as _retrieve_tool_context_impl,
    route_rag_tool_by_keyword as _route_rag_tool_by_keyword_impl,
    route_rag_tool_by_llm as _route_rag_tool_by_llm_impl,
    route_retrieval_flow_by_llm as _route_retrieval_flow_by_llm_impl,
)
from repositories.vector_repository import fetch_documents_by_source, list_vector_sources, search_vector_documents
from repositories.conversation_repository import load_chat_history
from services.rag.ictu_scope_service import is_ictu_related_query
from services.rag.langchain_retrievers import CorpusLexicalRetriever, VectorStoreRetriever
from services.llm.langchain_service import invoke_json_prompt_chain
from services.llm.llm_service import get_model, llm_network_available
from services.chat.memory_service import get_memory_store
from services.rag.rag_corpus import (
    _extract_relevant_snippet,
    _load_all_tool_documents,
    _load_tool_corpus,
    _normalize_for_match,
    _search_documents,
    _tokenize,
    clear_rag_corpus_cache,
)
from services.rag.rag_prompts import _RAW_TEXT_PROMPT, _build_rag_router_prompt, _build_retrieval_flow_prompt
from services.rag.rag_results import (
    _build_result_from_documents,
    _build_scope_guard_result,
    _build_web_knowledge_result,
    _build_web_search_result,
    _merge_web_search_result,
)
from services.rag.rag_types import (
    RETRIEVAL_HYBRID,
    RETRIEVAL_LOCAL_DATA,
    RETRIEVAL_LOCAL_FIRST,
    RETRIEVAL_WEB_FIRST,
    RETRIEVAL_WEB_SEARCH,
    CorpusDocument,
    RetrievalFlowPlan,
)
from services.vector.vector_store_service import embedding_backend_ready, inject_bot_rule
from services.content.web_search import should_use_web_search

_STUDENT_FAQ_ROUTE_CUES = (
    "khi nao",
    "bao gio",
    "o dau",
    "lam sao",
    "ntn",
)
_STUDENT_HANDBOOK_ROUTE_CUES = (
    "dieu kien dat danh hieu",
    "danh hieu sinh vien",
    "nguoi hoc khong duoc lam",
    "hanh vi nao",
    "chuong trinh dao tao",
    "tong so tin chi",
)
_SCHOOL_POLICY_ROUTE_CUES = (
    "bao hiem y te",
    "bhyt",
    "chinh sach",
    "lan 1",
    "lan 2",
    "lan 3",
)
_NORMALIZED_STUDENT_FAQ_ROUTE_CUES = tuple(_normalize_for_match(cue) for cue in _STUDENT_FAQ_ROUTE_CUES)
_NORMALIZED_STUDENT_HANDBOOK_ROUTE_CUES = tuple(_normalize_for_match(cue) for cue in _STUDENT_HANDBOOK_ROUTE_CUES)
_NORMALIZED_SCHOOL_POLICY_ROUTE_CUES = tuple(_normalize_for_match(cue) for cue in _SCHOOL_POLICY_ROUTE_CUES)
_ROUTE_CUE_BOOSTS = {
    "student_faq_rag": (_NORMALIZED_STUDENT_FAQ_ROUTE_CUES, 2),
    "student_handbook_rag": (_NORMALIZED_STUDENT_HANDBOOK_ROUTE_CUES, 4),
    "school_policy_rag": (_NORMALIZED_SCHOOL_POLICY_ROUTE_CUES, 4),
}


def _route_rag_tool_by_keyword(message: str) -> tuple[str, str]:
    return _route_rag_tool_by_keyword_impl(
        message,
        rag_tool_profiles=RAG_TOOL_PROFILES,
        fallback_rag_node=FALLBACK_RAG_NODE,
        normalize_for_match=_normalize_for_match,
        cue_boosts=_ROUTE_CUE_BOOSTS,
    )


def _keyword_route_score(route_name: str) -> int:
    return _keyword_route_score_impl(route_name)


def _extract_router_json(raw_text: str) -> Optional[dict]:
    return _extract_router_json_impl(raw_text)


def _llm_router_network_available() -> bool:
    return llm_network_available()


def _route_rag_tool_by_llm(message: str) -> Optional[tuple[str, str]]:
    return _route_rag_tool_by_llm_impl(
        message,
        raw_text_prompt=_RAW_TEXT_PROMPT,
        build_rag_router_prompt=_build_rag_router_prompt,
        invoke_json_prompt_chain=invoke_json_prompt_chain,
        get_model=get_model,
        llm_network_available=_llm_router_network_available,
        fallback_rag_node=FALLBACK_RAG_NODE,
        rag_tool_profiles=RAG_TOOL_PROFILES,
    )


def route_rag_tool(message: str) -> tuple[str, str]:
    keyword_result = _route_rag_tool_by_keyword(message)
    if keyword_result[0] != FALLBACK_RAG_NODE and _keyword_route_score(keyword_result[1]) >= 6:
        return keyword_result

    llm_result = _route_rag_tool_by_llm(message)
    if llm_result is not None:
        return llm_result
    return keyword_result


def _normalize_retrieval_source(value: object) -> Optional[str]:
    return _normalize_retrieval_source_impl(value)


def _normalize_retrieval_priority(value: object, source: str) -> str:
    return _normalize_retrieval_priority_impl(value, source)


def _fallback_retrieval_flow(message: str, *, route: str = "flow_keyword") -> RetrievalFlowPlan:
    return _fallback_retrieval_flow_impl(
        message,
        should_use_web_search=should_use_web_search,
        route=route,
    )


def _route_retrieval_flow_by_llm(message: str, rag_tool: Optional[str]) -> Optional[RetrievalFlowPlan]:
    return _route_retrieval_flow_by_llm_impl(
        message,
        rag_tool,
        raw_text_prompt=_RAW_TEXT_PROMPT,
        build_retrieval_flow_prompt=_build_retrieval_flow_prompt,
        invoke_json_prompt_chain=invoke_json_prompt_chain,
        get_model=get_model,
        llm_network_available=_llm_router_network_available,
    )


def route_retrieval_flow(message: str, rag_tool: Optional[str] = None) -> RetrievalFlowPlan:
    llm_result = _route_retrieval_flow_by_llm(message, rag_tool)
    if llm_result is not None:
        return llm_result
    return _fallback_retrieval_flow(message)


def _build_planned_web_result(message: str, route_name: str, tool_name: Optional[str]) -> Optional[RAGResult]:
    return _build_web_knowledge_result(message, route_name=route_name, tool_name=tool_name) or _build_web_search_result(
        message,
        route_name=route_name,
        tool_name=tool_name,
    )


def _build_retrieval_runtime() -> RetrievalRuntime:
    return RetrievalRuntime(
        is_ictu_related_query=is_ictu_related_query,
        route_retrieval_flow=route_retrieval_flow,
        build_scope_guard_result=_build_scope_guard_result,
        build_planned_web_result=_build_planned_web_result,
        merge_web_search_result=_merge_web_search_result,
        build_result_from_documents=_build_result_from_documents,
        corpus_lexical_retriever_cls=CorpusLexicalRetriever,
        vector_store_retriever_cls=VectorStoreRetriever,
        load_tool_corpus=_load_tool_corpus,
        load_all_tool_documents=_load_all_tool_documents,
        search_documents=_search_documents,
        extract_relevant_snippet=_extract_relevant_snippet,
        inject_bot_rule=inject_bot_rule,
        embedding_backend_ready=embedding_backend_ready,
        session_memory=get_memory_store(),
        history_loader=load_chat_history,
        list_vector_sources=list_vector_sources,
        fetch_documents_by_source=fetch_documents_by_source,
        search_vector_documents=search_vector_documents,
        default_rag_tool=DEFAULT_RAG_TOOL,
        fallback_rag_node=FALLBACK_RAG_NODE,
        rag_tool_order=tuple(RAG_TOOL_ORDER),
    )


def build_retrieval_query(session_id: str, message: str) -> str:
    return _build_retrieval_query_impl(_build_retrieval_runtime(), session_id, message)


def retrieve_tool_context(
    message: str,
    session_id: str,
    tool_name: str,
    route_name: str,
    retrieval_plan: Optional[RetrievalFlowPlan] = None,
) -> RAGResult:
    return _retrieve_tool_context_impl(
        _build_retrieval_runtime(),
        message=message,
        session_id=session_id,
        tool_name=tool_name,
        route_name=route_name,
        retrieval_plan=retrieval_plan,
    )


def retrieve_fallback_context(
    message: str,
    session_id: str,
    route_name: str = "router_fallback",
    retrieval_plan: Optional[RetrievalFlowPlan] = None,
) -> RAGResult:
    return _retrieve_fallback_context_impl(
        _build_retrieval_runtime(),
        message=message,
        session_id=session_id,
        route_name=route_name,
        retrieval_plan=retrieval_plan,
    )


def retrieve_general_context(
    message: str,
    session_id: str,
    route_name: str = "general_fallback",
    tool_name: Optional[str] = None,
    retrieval_plan: Optional[RetrievalFlowPlan] = None,
) -> RAGResult:
    return _retrieve_general_context_impl(
        _build_retrieval_runtime(),
        message=message,
        session_id=session_id,
        route_name=route_name,
        tool_name=tool_name,
        retrieval_plan=retrieval_plan,
    )


def retrieve_context(message: str, session_id: str) -> RAGResult:
    return retrieve_general_context(message, session_id)

