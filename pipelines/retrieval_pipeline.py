from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from models.chat import RAGResult
from services.rag.ictu_scope_service import normalize_scope_text
from services.rag.rag_types import (
    RETRIEVAL_HYBRID,
    RETRIEVAL_LOCAL_DATA,
    RETRIEVAL_LOCAL_FIRST,
    RETRIEVAL_WEB_FIRST,
    RETRIEVAL_WEB_SEARCH,
    CorpusDocument,
    RetrievalFlowPlan,
)


TOOL_LEXICAL_RETRIEVAL_LIMIT = 8
FALLBACK_LEXICAL_RETRIEVAL_LIMIT = 8
ROUTER_REQUEST_TIMEOUT_SECONDS = 10
ROUTER_EXECUTOR_TIMEOUT_SECONDS = 4
FOLLOW_UP_MAX_TOKENS = 3
FOLLOW_UP_PREFIX_MAX_TOKENS = 6
_FOLLOW_UP_QUERY_PREFIXES = tuple(
    normalize_scope_text(marker)
    for marker in (
        "còn",
        "thế còn",
        "vậy còn",
        "thế",
        "vậy",
        "chi tiết",
        "cụ thể",
        "thêm",
        "nữa",
        "ý là",
    )
)
_SELF_CONTAINED_QUERY_MARKERS = tuple(
    normalize_scope_text(marker)
    for marker in (
        "ictu",
        "trường",
        "đại học",
        "ngành",
        "điểm chuẩn",
        "tuyển sinh",
        "học phí",
        "học bổng",
        "miễn giảm",
        "thông báo",
        "lịch",
        "lịch học",
        "lịch thi",
        "tốt nghiệp",
        "bhyt",
        "bảo hiểm",
        "chương trình",
        "tín chỉ",
        "email",
        "hồ sơ",
    )
)


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


def extract_router_json(raw_text: str) -> Optional[dict]:
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


def keyword_route_score(route_name: str) -> int:
    match = re.search(r"router_keyword_score:(\d+)", route_name)
    if not match:
        return 0
    return int(match.group(1))


def route_rag_tool_by_keyword(
    message: str,
    *,
    rag_tool_profiles: Mapping[str, Mapping[str, Any]],
    fallback_rag_node: str,
    normalize_for_match: Callable[[str], str],
    cue_boosts: Mapping[str, tuple[tuple[str, ...], int]],
) -> tuple[str, str]:
    message_lower = normalize_for_match(message)
    scores: dict[str, int] = {}

    for tool_name, profile in rag_tool_profiles.items():
        keywords = [normalize_for_match(keyword) for keyword in profile.get("route_keywords", [])]
        score = sum(2 for keyword in keywords if keyword in message_lower)
        boost_cues, bonus = cue_boosts.get(tool_name, ((), 0))
        if bonus and any(cue in message_lower for cue in boost_cues):
            score += bonus
        scores[tool_name] = score

    best_tool = max(scores, key=scores.get)
    best_score = scores[best_tool]
    if best_score <= 0:
        return fallback_rag_node, "router_fallback"
    return best_tool, f"router_keyword_score:{best_score}"


def _run_llm_json_decision(
    *,
    prompt_text: str,
    raw_text_prompt: Any,
    invoke_json_prompt_chain: Callable[..., tuple[Optional[dict[str, Any]], str, str]],
    get_model: Callable[[], Any],
    llm_network_available: Callable[[], bool],
    generation_config: dict[str, Any],
    request_timeout: int,
    future_timeout: int,
    timeout_message: str,
    error_message: str,
    switch_message: str,
) -> Optional[dict[str, Any]]:
    if get_model() is None or not llm_network_available():
        return None

    try:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            invoke_json_prompt_chain,
            raw_text_prompt,
            {"prompt": prompt_text},
            generation_config=generation_config,
            request_options={"timeout": request_timeout},
            rotate=False,
        )
        try:
            payload, raw_text, used_model = future.result(timeout=future_timeout)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        primary_model = get_model()
        if primary_model is not None and used_model != primary_model.label:
            print(switch_message.format(model=used_model))
        return payload or extract_router_json(raw_text)
    except FutureTimeoutError:
        print(timeout_message)
    except Exception as exc:
        print(f"{error_message}: {exc}")
    return None


def route_rag_tool_by_llm(
    message: str,
    *,
    raw_text_prompt: Any,
    build_rag_router_prompt: Callable[[str], str],
    invoke_json_prompt_chain: Callable[..., tuple[Optional[dict[str, Any]], str, str]],
    get_model: Callable[[], Any],
    llm_network_available: Callable[[], bool],
    fallback_rag_node: str,
    rag_tool_profiles: Mapping[str, Mapping[str, Any]],
) -> Optional[tuple[str, str]]:
    payload = _run_llm_json_decision(
        prompt_text=build_rag_router_prompt(message),
        raw_text_prompt=raw_text_prompt,
        invoke_json_prompt_chain=invoke_json_prompt_chain,
        get_model=get_model,
        llm_network_available=llm_network_available,
        generation_config={"temperature": 0, "max_output_tokens": 180, "response_mime_type": "application/json"},
        request_timeout=ROUTER_REQUEST_TIMEOUT_SECONDS,
        future_timeout=ROUTER_EXECUTOR_TIMEOUT_SECONDS,
        timeout_message="LLM router timed out, falling back to keyword routing.",
        error_message="LLM router unavailable, falling back to keyword routing",
        switch_message="LLM router switched to fallback model: {model}",
    )
    if not payload:
        return None

    tool_name = str(payload.get("tool", "")).strip()
    try:
        confidence = float(payload.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0

    if tool_name == fallback_rag_node:
        return fallback_rag_node, f"router_llm:{confidence:.2f}"
    if tool_name in rag_tool_profiles:
        if confidence < 0.25:
            return fallback_rag_node, f"router_llm_low_conf:{confidence:.2f}"
        return tool_name, f"router_llm:{tool_name}:{confidence:.2f}"
    return None


def normalize_retrieval_source(value: object) -> Optional[str]:
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


def normalize_retrieval_priority(value: object, source: str) -> str:
    priority = str(value or "").strip().casefold()
    if priority in {RETRIEVAL_LOCAL_FIRST, "local", "data", "rag"}:
        return RETRIEVAL_LOCAL_FIRST
    if priority in {RETRIEVAL_WEB_FIRST, "web", "search", "online"}:
        return RETRIEVAL_WEB_FIRST
    if source == RETRIEVAL_WEB_SEARCH:
        return RETRIEVAL_WEB_FIRST
    return RETRIEVAL_LOCAL_FIRST


def fallback_retrieval_flow(
    message: str,
    *,
    should_use_web_search: Callable[[str], bool],
    route: str = "flow_keyword",
) -> RetrievalFlowPlan:
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


def route_retrieval_flow_by_llm(
    message: str,
    rag_tool: Optional[str],
    *,
    raw_text_prompt: Any,
    build_retrieval_flow_prompt: Callable[[str, Optional[str]], str],
    invoke_json_prompt_chain: Callable[..., tuple[Optional[dict[str, Any]], str, str]],
    get_model: Callable[[], Any],
    llm_network_available: Callable[[], bool],
) -> Optional[RetrievalFlowPlan]:
    payload = _run_llm_json_decision(
        prompt_text=build_retrieval_flow_prompt(message, rag_tool),
        raw_text_prompt=raw_text_prompt,
        invoke_json_prompt_chain=invoke_json_prompt_chain,
        get_model=get_model,
        llm_network_available=llm_network_available,
        generation_config={"temperature": 0, "max_output_tokens": 220, "response_mime_type": "application/json"},
        request_timeout=ROUTER_REQUEST_TIMEOUT_SECONDS,
        future_timeout=ROUTER_EXECUTOR_TIMEOUT_SECONDS,
        timeout_message="Retrieval flow planner timed out, falling back to keyword flow.",
        error_message="Retrieval flow planner unavailable, falling back to keyword flow",
        switch_message="Retrieval flow planner switched to fallback model: {model}",
    )
    if not payload:
        return None

    source = normalize_retrieval_source(payload.get("source"))
    if source is None:
        return None
    priority = normalize_retrieval_priority(payload.get("priority"), source)
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


def _contains_normalized_marker(text: str, markers: tuple[str, ...]) -> bool:
    padded_text = f" {text} "
    return any(f" {marker} " in padded_text for marker in markers)


def _starts_with_normalized_prefix(text: str, prefixes: tuple[str, ...]) -> bool:
    return any(text == prefix or text.startswith(f"{prefix} ") for prefix in prefixes)


def _should_expand_with_previous_query(previous_q: str, current_message: str) -> bool:
    normalized_previous = normalize_scope_text(previous_q)
    normalized_current = normalize_scope_text(current_message)
    if not normalized_previous or not normalized_current or normalized_previous == normalized_current:
        return False

    current_tokens = normalized_current.split()
    if not current_tokens:
        return False

    has_follow_up_prefix = _starts_with_normalized_prefix(normalized_current, _FOLLOW_UP_QUERY_PREFIXES)
    if has_follow_up_prefix:
        return len(current_tokens) <= FOLLOW_UP_PREFIX_MAX_TOKENS

    if _contains_normalized_marker(normalized_current, _SELF_CONTAINED_QUERY_MARKERS):
        return False

    if len(current_tokens) <= FOLLOW_UP_MAX_TOKENS:
        return True

    return False


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
    if not _should_expand_with_previous_query(previous_q, current_message):
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
