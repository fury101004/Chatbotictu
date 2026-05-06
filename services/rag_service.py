from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from functools import lru_cache
from typing import Optional
import json
import re

from config.db import get_chat_history
from config.rag_tools import DEFAULT_RAG_TOOL, FALLBACK_RAG_NODE, RAG_TOOL_ORDER, RAG_TOOL_PROFILES
from models.chat import RAGResult
from services.ictu_scope_service import is_ictu_related_query
from services.langchain_service import invoke_json_prompt_chain
from services.langchain_retrievers import CorpusLexicalRetriever, VectorStoreRetriever
from services.llm_service import get_model, llm_network_available
from services.rag_corpus import (
    _extract_relevant_snippet,
    _load_all_tool_documents,
    _load_tool_corpus,
    _normalize_for_match,
    _search_documents,
    _tokenize,
    clear_rag_corpus_cache,
    detect_target_file,
)
from services.rag_prompts import _RAW_TEXT_PROMPT, _build_rag_router_prompt, _build_retrieval_flow_prompt
from services.rag_results import (
    _build_result_from_documents,
    _build_result_from_matches,
    _build_scope_guard_result,
    _build_web_knowledge_result,
    _build_web_search_result,
    _merge_web_search_result,
    build_context_from_chunks,
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
from services.vector_store_service import SESSION_MEMORY, embedding_backend_ready, get_collection, inject_bot_rule, query_documents
from services.web_search import should_use_web_search

TOOL_LEXICAL_RETRIEVAL_LIMIT = 8
FALLBACK_LEXICAL_RETRIEVAL_LIMIT = 8


def _route_rag_tool_by_keyword(message: str) -> tuple[str, str]:
    message_lower = _normalize_for_match(message)
    scores: dict[str, int] = {}

    for tool_name, profile in RAG_TOOL_PROFILES.items():
        keywords = [_normalize_for_match(keyword) for keyword in profile.get("route_keywords", [])]
        score = sum(2 for keyword in keywords if keyword in message_lower)
        if tool_name == "student_faq_rag" and any(
            cue in message_lower for cue in ["khi nao", "bao gio", "o dau", "lam sao", "ntn"]
        ):
            score += 2
        if tool_name == "student_handbook_rag" and any(
            cue in message_lower
            for cue in [
                "dieu kien dat danh hieu",
                "danh hieu sinh vien",
                "nguoi hoc khong duoc lam",
                "hanh vi nao",
                "chuong trinh dao tao",
                "tong so tin chi",
            ]
        ):
            score += 4
        if tool_name == "school_policy_rag" and any(
            cue in message_lower for cue in ["bao hiem y te", "bhyt", "chinh sach", "lan 1", "lan 2", "lan 3"]
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


@lru_cache(maxsize=1)
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
        print("LLM router bị timeout, chuyển sang keyword routing.")
    except Exception as exc:
        print(f"LLM router không khả dụng, chuyển sang keyword routing: {exc}")

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
            reason="Câu hỏi có dấu hiệu cần thông tin mới/cập nhật.",
            confidence=0.55,
            route=f"{route}:web_search",
        )
    return RetrievalFlowPlan(
        source=RETRIEVAL_LOCAL_DATA,
        priority=RETRIEVAL_LOCAL_FIRST,
        reason="Mặc định ưu tiên dữ liệu nội bộ khi không có dấu hiệu thời gian thực.",
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
            print(f"Retrieval flow planner chuyển sang model fallback: {used_model}")

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
        print("Retrieval flow planner bị timeout, chuyển sang keyword flow.")
    except Exception as exc:
        print(f"Retrieval flow planner không khả dụng, chuyển sang keyword flow: {exc}")
    return None


def route_retrieval_flow(message: str, rag_tool: Optional[str] = None) -> RetrievalFlowPlan:
    llm_result = _route_retrieval_flow_by_llm(message, rag_tool)
    if llm_result is not None:
        return llm_result
    return _fallback_retrieval_flow(message)


def _plan_allows_web(plan: RetrievalFlowPlan) -> bool:
    return plan.source in {RETRIEVAL_WEB_SEARCH, RETRIEVAL_HYBRID}


def _plan_is_web_first(plan: RetrievalFlowPlan) -> bool:
    return plan.priority == RETRIEVAL_WEB_FIRST or plan.source == RETRIEVAL_WEB_SEARCH


def _build_planned_web_result(message: str, route_name: str, tool_name: Optional[str]) -> Optional[RAGResult]:
    return _build_web_knowledge_result(message, route_name=route_name, tool_name=tool_name) or _build_web_search_result(
        message,
        route_name=route_name,
        tool_name=tool_name,
    )


def retrieve_tool_context(
    message: str,
    session_id: str,
    tool_name: str,
    route_name: str,
    retrieval_plan: Optional[RetrievalFlowPlan] = None,
) -> RAGResult:
    scope_query = build_retrieval_query(session_id, message)
    if not is_ictu_related_query(scope_query):
        return _build_scope_guard_result(route_name=route_name, tool_name=tool_name)

    flow_plan = retrieval_plan or route_retrieval_flow(scope_query, tool_name)
    planned_route_name = f"{route_name}|{flow_plan.route}"
    web_result: Optional[RAGResult] = None

    if _plan_allows_web(flow_plan) and _plan_is_web_first(flow_plan):
        web_result = _build_planned_web_result(scope_query, route_name=planned_route_name, tool_name=tool_name)
        if web_result is not None and flow_plan.source == RETRIEVAL_WEB_SEARCH:
            return web_result

    lexical_documents = CorpusLexicalRetriever(
        document_supplier=lambda: _load_tool_corpus(tool_name),
        search_fn=_search_documents,
        snippet_fn=_extract_relevant_snippet,
        tool_name=tool_name,
        limit=TOOL_LEXICAL_RETRIEVAL_LIMIT,
    ).invoke(message)

    if not lexical_documents:
        if web_result is not None:
            return web_result
        if _plan_allows_web(flow_plan):
            web_result = _build_planned_web_result(scope_query, route_name=planned_route_name, tool_name=tool_name)
            if web_result is not None:
                return web_result
        return retrieve_general_context(
            message,
            session_id,
            route_name=planned_route_name,
            tool_name=tool_name,
            retrieval_plan=flow_plan,
        )

    inject_bot_rule(force_full=True)
    result = _build_result_from_documents(
        documents=lexical_documents,
        tool_name=tool_name,
        route_name=planned_route_name,
        mode=tool_name,
    )

    if flow_plan.source == RETRIEVAL_WEB_SEARCH:
        web_result = web_result or _build_planned_web_result(scope_query, route_name=planned_route_name, tool_name=tool_name)
        return web_result or result

    if flow_plan.source == RETRIEVAL_HYBRID:
        web_result = web_result or _build_planned_web_result(scope_query, route_name=planned_route_name, tool_name=tool_name)
        return _merge_web_search_result(
            result,
            web_result,
            web_first=_plan_is_web_first(flow_plan),
        )

    return result


def retrieve_fallback_context(
    message: str,
    session_id: str,
    route_name: str = "router_fallback",
    retrieval_plan: Optional[RetrievalFlowPlan] = None,
) -> RAGResult:
    scope_query = build_retrieval_query(session_id, message)
    if not is_ictu_related_query(scope_query):
        return _build_scope_guard_result(route_name=route_name, tool_name=FALLBACK_RAG_NODE)

    flow_plan = retrieval_plan or route_retrieval_flow(scope_query, FALLBACK_RAG_NODE)
    planned_route_name = f"{route_name}|{flow_plan.route}"
    web_result: Optional[RAGResult] = None

    if _plan_allows_web(flow_plan) and _plan_is_web_first(flow_plan):
        web_result = _build_planned_web_result(scope_query, route_name=planned_route_name, tool_name=FALLBACK_RAG_NODE)
        if web_result is not None and flow_plan.source == RETRIEVAL_WEB_SEARCH:
            return web_result

    def _fallback_search(_: tuple[CorpusDocument, ...], query: str, limit: int = 6) -> list[tuple[int, CorpusDocument]]:
        all_matches: list[tuple[int, CorpusDocument]] = []
        for tool in RAG_TOOL_ORDER:
            documents = _load_tool_corpus(tool)
            all_matches.extend(_search_documents(documents, query, limit=2))
        all_matches.sort(key=lambda item: item[0], reverse=True)
        return all_matches[:limit]

    fallback_documents = CorpusLexicalRetriever(
        document_supplier=_load_all_tool_documents,
        search_fn=_fallback_search,
        snippet_fn=_extract_relevant_snippet,
        tool_name=FALLBACK_RAG_NODE,
        limit=FALLBACK_LEXICAL_RETRIEVAL_LIMIT,
    ).invoke(message)

    if not fallback_documents:
        if web_result is not None:
            return web_result
        if _plan_allows_web(flow_plan):
            web_result = _build_planned_web_result(scope_query, route_name=planned_route_name, tool_name=FALLBACK_RAG_NODE)
            if web_result is not None:
                return web_result
        return retrieve_general_context(
            message,
            session_id,
            route_name=planned_route_name,
            tool_name=DEFAULT_RAG_TOOL,
            retrieval_plan=flow_plan,
        )

    inject_bot_rule(force_full=True)
    result = _build_result_from_documents(
        documents=fallback_documents,
        tool_name=FALLBACK_RAG_NODE,
        route_name=planned_route_name,
        mode="multi_tool_fallback_rag",
    )

    if flow_plan.source == RETRIEVAL_WEB_SEARCH:
        web_result = web_result or _build_planned_web_result(scope_query, route_name=planned_route_name, tool_name=FALLBACK_RAG_NODE)
        return web_result or result

    if flow_plan.source == RETRIEVAL_HYBRID:
        web_result = web_result or _build_planned_web_result(scope_query, route_name=planned_route_name, tool_name=FALLBACK_RAG_NODE)
        return _merge_web_search_result(
            result,
            web_result,
            web_first=_plan_is_web_first(flow_plan),
        )

    return result


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


def _normalize_message_key(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().casefold()


def _get_previous_user_message_from_db(session_id: str, current_message: str) -> str:
    try:
        history = get_chat_history(session_id=session_id)
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


def build_retrieval_query(session_id: str, message: str) -> str:
    current_message = str(message or "").strip()
    if not current_message:
        return ""

    previous_q = ""
    history = SESSION_MEMORY.get(session_id)
    if history:
        previous_q = str(history[-1].get("query") or "").strip()
    if not previous_q:
        previous_q = _get_previous_user_message_from_db(session_id, current_message)

    if not previous_q:
        return current_message
    if _normalize_message_key(previous_q) == _normalize_message_key(current_message):
        return current_message
    return f"{previous_q} {current_message}"


def _build_general_fallback_result(
    message: str,
    route_name: str,
    tool_name: Optional[str],
    retrieval_plan: Optional[RetrievalFlowPlan] = None,
) -> RAGResult:
    flow_plan = retrieval_plan or route_retrieval_flow(message, tool_name)
    web_result: Optional[RAGResult] = None

    if _plan_allows_web(flow_plan) and _plan_is_web_first(flow_plan):
        web_result = _build_planned_web_result(message, route_name=route_name, tool_name=tool_name)
        if web_result is not None and flow_plan.source == RETRIEVAL_WEB_SEARCH:
            return web_result

    fallback_documents = CorpusLexicalRetriever(
        document_supplier=_load_all_tool_documents,
        search_fn=_search_documents,
        snippet_fn=_extract_relevant_snippet,
        tool_name=tool_name or FALLBACK_RAG_NODE,
        limit=FALLBACK_LEXICAL_RETRIEVAL_LIMIT,
    ).invoke(message)
    if fallback_documents:
        result = _build_result_from_documents(
            documents=fallback_documents,
            tool_name=tool_name or FALLBACK_RAG_NODE,
            route_name=route_name,
            mode="lexical_fallback",
        )

        if flow_plan.source == RETRIEVAL_WEB_SEARCH:
            web_result = web_result or _build_planned_web_result(message, route_name=route_name, tool_name=tool_name)
            return web_result or result

        if flow_plan.source == RETRIEVAL_HYBRID:
            web_result = web_result or _build_planned_web_result(message, route_name=route_name, tool_name=tool_name)
            return _merge_web_search_result(
                result,
                web_result,
                web_first=_plan_is_web_first(flow_plan),
            )

        return result

    result = RAGResult(
        context_text="Thông tin đang được cập nhật.",
        chunks=[],
        target_file=None,
        mode="lexical_fallback_empty",
        sources=[],
        chunks_used=0,
        rag_tool=tool_name,
        rag_route=route_name,
    )

    if _plan_allows_web(flow_plan):
        return _merge_web_search_result(
            result,
            web_result or _build_planned_web_result(message, route_name=route_name, tool_name=tool_name),
            web_first=_plan_is_web_first(flow_plan),
        )
    return result


def retrieve_general_context(
    message: str,
    session_id: str,
    route_name: str = "general_fallback",
    tool_name: Optional[str] = None,
    retrieval_plan: Optional[RetrievalFlowPlan] = None,
) -> RAGResult:
    query_for_retrieval = build_retrieval_query(session_id, message)
    if not is_ictu_related_query(query_for_retrieval):
        return _build_scope_guard_result(route_name=route_name, tool_name=tool_name)

    flow_plan = retrieval_plan or route_retrieval_flow(query_for_retrieval, tool_name)
    planned_route_name = route_name if f"|{flow_plan.route}" in route_name else f"{route_name}|{flow_plan.route}"
    web_result: Optional[RAGResult] = None

    if _plan_allows_web(flow_plan) and _plan_is_web_first(flow_plan):
        web_result = _build_planned_web_result(query_for_retrieval, route_name=planned_route_name, tool_name=tool_name)
        if web_result is not None and flow_plan.source == RETRIEVAL_WEB_SEARCH:
            return web_result

    message_lower = message.lower()
    target_file = None

    if not embedding_backend_ready():
        return _build_general_fallback_result(message, planned_route_name, tool_name, retrieval_plan=flow_plan)

    try:
        target_file = _detect_collection_source(message_lower)
        documents = VectorStoreRetriever(
            query_fn=query_documents,
            collection_getter=get_collection,
            user_id=session_id,
            n_results=100,
            alpha=0.7,
            target_source=target_file,
        ).invoke(query_for_retrieval)
        mode = "forced_file" if target_file else "hybrid_search"
    except Exception as exc:
        print(f"Vector retrieval unavailable, using lexical fallback: {exc}")
        return _build_general_fallback_result(message, planned_route_name, tool_name, retrieval_plan=flow_plan)

    inject_bot_rule(force_full=True)
    result = _build_result_from_documents(
        documents=documents,
        tool_name=tool_name,
        route_name=planned_route_name,
        mode=mode,
        target_file=target_file,
        context_max_chunks=25,
    )
    unique_sources = result.sources

    if flow_plan.source == RETRIEVAL_WEB_SEARCH:
        web_result = web_result or _build_planned_web_result(query_for_retrieval, route_name=planned_route_name, tool_name=tool_name)
        return web_result or result

    if flow_plan.source == RETRIEVAL_HYBRID or (not unique_sources and _plan_allows_web(flow_plan)):
        web_result = web_result or _build_planned_web_result(query_for_retrieval, route_name=planned_route_name, tool_name=tool_name)
        return _merge_web_search_result(
            result,
            web_result,
            web_first=_plan_is_web_first(flow_plan),
        )

    return result


def retrieve_context(message: str, session_id: str) -> RAGResult:
    return retrieve_general_context(message, session_id)
