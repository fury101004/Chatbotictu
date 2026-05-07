from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Optional

from config.rag_tools import DEFAULT_RAG_TOOL, FALLBACK_RAG_NODE, RAG_TOOL_ORDER, RAG_TOOL_PROFILES
from models.chat import RAGResult
from pipelines.retrieval_pipeline import (
    RetrievalRuntime,
    build_retrieval_query as _build_retrieval_query_impl,
    retrieve_fallback_context as _retrieve_fallback_context_impl,
    retrieve_general_context as _retrieve_general_context_impl,
    retrieve_tool_context as _retrieve_tool_context_impl,
)
from repositories.vector_repository import fetch_documents_by_source, list_vector_sources, search_vector_documents
from repositories.conversation_repository import load_chat_history
from services.ictu_scope_service import is_ictu_related_query
from services.langchain_retrievers import CorpusLexicalRetriever, VectorStoreRetriever
from services.langchain_service import invoke_json_prompt_chain
from services.llm_service import get_model, llm_network_available
from services.memory_service import get_memory_store
from services.rag_corpus import (
    _extract_relevant_snippet,
    _load_all_tool_documents,
    _load_tool_corpus,
    _normalize_for_match,
    _search_documents,
    _tokenize,
    clear_rag_corpus_cache,
)
from services.rag_prompts import _RAW_TEXT_PROMPT, _build_rag_router_prompt, _build_retrieval_flow_prompt
from services.rag_results import (
    _build_result_from_documents,
    _build_scope_guard_result,
    _build_web_knowledge_result,
    _build_web_search_result,
    _merge_web_search_result,
)
from services.rag_types import (
    RETRIEVAL_HYBRID,
    RETRIEVAL_LOCAL_DATA,
    RETRIEVAL_LOCAL_FIRST,
    RETRIEVAL_WEB_FIRST,
    RETRIEVAL_WEB_SEARCH,
    CorpusDocument,
    RetrievalFlowPlan,
)
from services.vector_store_service import embedding_backend_ready, inject_bot_rule
from services.web_search import should_use_web_search

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


def _route_rag_tool_by_keyword(message: str) -> tuple[str, str]:
    message_lower = _normalize_for_match(message)
    scores: dict[str, int] = {}

    for tool_name, profile in RAG_TOOL_PROFILES.items():
        keywords = [_normalize_for_match(keyword) for keyword in profile.get("route_keywords", [])]
        score = sum(2 for keyword in keywords if keyword in message_lower)
        if tool_name == "student_faq_rag" and any(cue in message_lower for cue in _NORMALIZED_STUDENT_FAQ_ROUTE_CUES):
            score += 2
        if tool_name == "student_handbook_rag" and any(
            cue in message_lower for cue in _NORMALIZED_STUDENT_HANDBOOK_ROUTE_CUES
        ):
            score += 4
        if tool_name == "school_policy_rag" and any(
            cue in message_lower for cue in _NORMALIZED_SCHOOL_POLICY_ROUTE_CUES
        ):
            score += 4
        scores[tool_name] = score

    best_tool = max(scores, key=scores.get)
    best_score = scores[best_tool]

    if best_score <= 0:
        return FALLBACK_RAG_NODE, "router_fallback"

    return best_tool, f"router_keyword_score:{best_score}"


def _keyword_route_score(route_name: str) -> int:
    match = re.search(r"router_keyword_score:(\d+)", route_name)
    if not match:
        return 0
    return int(match.group(1))


def _extract_router_json(raw_text: str) -> Optional[dict]:
    if not raw_text:
        return None

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _llm_router_network_available() -> bool:
    return llm_network_available()


def _route_rag_tool_by_llm(message: str) -> Optional[tuple[str, str]]:
    if get_model() is None or not _llm_router_network_available():
        return None

    try:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            invoke_json_prompt_chain,
            _RAW_TEXT_PROMPT,
            {"prompt": _build_rag_router_prompt(message)},
            generation_config={"temperature": 0, "max_output_tokens": 180, "response_mime_type": "application/json"},
            request_options={"timeout": 10},
            rotate=False,
        )
        try:
            payload, raw_text, used_model = future.result(timeout=4)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        primary_model = get_model()
        if primary_model is not None and used_model != primary_model.label:
            print(f"LLM router switched to fallback model: {used_model}")
        payload = payload or _extract_router_json(raw_text)
        if not payload:
            return None

        tool_name = str(payload.get("tool", "")).strip()
        try:
            confidence = float(payload.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0

        if tool_name == FALLBACK_RAG_NODE:
            return FALLBACK_RAG_NODE, f"router_llm:{confidence:.2f}"
        if tool_name in RAG_TOOL_PROFILES:
            if confidence < 0.25:
                return FALLBACK_RAG_NODE, f"router_llm_low_conf:{confidence:.2f}"
            return tool_name, f"router_llm:{tool_name}:{confidence:.2f}"
    except FutureTimeoutError:
        print("LLM router timed out, falling back to keyword routing.")
    except Exception as exc:
        print(f"LLM router unavailable, falling back to keyword routing: {exc}")

    return None


def route_rag_tool(message: str) -> tuple[str, str]:
    keyword_result = _route_rag_tool_by_keyword(message)
    if keyword_result[0] != FALLBACK_RAG_NODE and _keyword_route_score(keyword_result[1]) >= 6:
        return keyword_result

    llm_result = _route_rag_tool_by_llm(message)
    if llm_result is not None:
        return llm_result
    return keyword_result


def _normalize_retrieval_source(value: object) -> Optional[str]:
    source = str(value or "").strip().casefold()
    aliases = {
        "local": RETRIEVAL_LOCAL_DATA,
        "data": RETRIEVAL_LOCAL_DATA,
        "local_data": RETRIEVAL_LOCAL_DATA,
        "rag": RETRIEVAL_LOCAL_DATA,
        "vector": RETRIEVAL_LOCAL_DATA,
        "web": RETRIEVAL_WEB_SEARCH,
        "web_search": RETRIEVAL_WEB_SEARCH,
        "search": RETRIEVAL_WEB_SEARCH,
        "online": RETRIEVAL_WEB_SEARCH,
        "hybrid": RETRIEVAL_HYBRID,
        "both": RETRIEVAL_HYBRID,
        "local_and_web": RETRIEVAL_HYBRID,
    }
    return aliases.get(source)


def _normalize_retrieval_priority(value: object, source: str) -> str:
    priority = str(value or "").strip().casefold()
    if priority in {RETRIEVAL_LOCAL_FIRST, "local", "data", "rag"}:
        return RETRIEVAL_LOCAL_FIRST
    if priority in {RETRIEVAL_WEB_FIRST, "web", "search", "online"}:
        return RETRIEVAL_WEB_FIRST
    if source == RETRIEVAL_WEB_SEARCH:
        return RETRIEVAL_WEB_FIRST
    return RETRIEVAL_LOCAL_FIRST


def _fallback_retrieval_flow(message: str, *, route: str = "flow_keyword") -> RetrievalFlowPlan:
    if should_use_web_search(message):
        return RetrievalFlowPlan(
            source=RETRIEVAL_WEB_SEARCH,
            priority=RETRIEVAL_WEB_FIRST,
            reason="Realtime query likely needs web data.",
            confidence=0.55,
            route=f"{route}:web_search",
        )
    return RetrievalFlowPlan(
        source=RETRIEVAL_LOCAL_DATA,
        priority=RETRIEVAL_LOCAL_FIRST,
        reason="Default to internal data for stable institutional questions.",
        confidence=0.50,
        route=f"{route}:local_data",
    )


def _route_retrieval_flow_by_llm(message: str, rag_tool: Optional[str]) -> Optional[RetrievalFlowPlan]:
    if get_model() is None or not _llm_router_network_available():
        return None

    try:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            invoke_json_prompt_chain,
            _RAW_TEXT_PROMPT,
            {"prompt": _build_retrieval_flow_prompt(message, rag_tool)},
            generation_config={"temperature": 0, "max_output_tokens": 220, "response_mime_type": "application/json"},
            request_options={"timeout": 10},
            rotate=False,
        )
        try:
            payload, raw_text, used_model = future.result(timeout=4)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        primary_model = get_model()
        if primary_model is not None and used_model != primary_model.label:
            print(f"Retrieval flow planner switched to fallback model: {used_model}")

        payload = payload or _extract_router_json(raw_text)
        if not payload:
            return None

        source = _normalize_retrieval_source(payload.get("source"))
        if source is None:
            return None
        priority = _normalize_retrieval_priority(payload.get("priority"), source)
        try:
            confidence = float(payload.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        reason = str(payload.get("reason") or "").strip()[:240]

        if confidence < 0.25:
            return None

        return RetrievalFlowPlan(
            source=source,
            priority=priority,
            reason=reason or "LLM retrieval flow planner.",
            confidence=max(0.0, min(confidence, 1.0)),
            route=f"flow_llm:{source}:{priority}:{confidence:.2f}",
        )
    except FutureTimeoutError:
        print("Retrieval flow planner timed out, falling back to keyword flow.")
    except Exception as exc:
        print(f"Retrieval flow planner unavailable, falling back to keyword flow: {exc}")
    return None


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
