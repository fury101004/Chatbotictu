from __future__ import annotations

import logging
import re
import time
from functools import lru_cache

from orchestrators.chat_orchestrator import build_chat_response_payload
from orchestrators.rag_orchestrator import retrieve_context as retrieve_rag_context, route_tool as route_rag_tool_via_orchestrator
from config.settings import settings
from config.rag_tools import DEFAULT_RAG_TOOL
from models.chat import ChatGraphState, RAGResult
from repositories.conversation_repository import load_chat_history, save_conversation_message
from shared.prompt_loader import render_prompt
from services.chat.intent_service import detect_intent, get_intent_response
from services.chat.contextual_query_service import is_source_year_follow_up, rewrite_contextual_question
from services.rag.ictu_scope_service import normalize_scope_text
from services.chat.memory_service import append_retrieval_memory, get_last_retrieval_years
from services.chat.moderation_service import contains_swear, get_swear_response
from services.chat.multilingual_service import chat_multilingual, get_current_language
from services.chat.quick_reply_service import get_quick_response
from services.content.web_knowledge_service import save_web_search_answer
from services.eval_tracker import get_eval_tracker
from services.llm.graph_service import RAGChatGraph
from services.memory_store import get_default_memory_store, stable_session_id


logger = logging.getLogger("chat_agent")
save_message = save_conversation_message

_MISSING_CONTEXT_TEXTS = (
    "",
    "Thông tin đang được cập nhật.",
    "Thông tin này hiện chưa có trong tài liệu của em.",
)
_NORMALIZED_MISSING_CONTEXT_TEXTS = tuple(normalize_scope_text(marker) for marker in _MISSING_CONTEXT_TEXTS)
_NO_INFO_RESPONSES = (
    "Thông tin này hiện chưa có trong tài liệu của em.",
    "Không tìm thấy thông tin này trong sổ tay sinh viên.",
    "This information is not currently available in my documents.",
    "I could not find this information in the student handbook.",
)
_NORMALIZED_NO_INFO_RESPONSES = tuple(normalize_scope_text(marker) for marker in _NO_INFO_RESPONSES)
_AMBIGUOUS_YEAR_RE = re.compile(r"\b20\d{2}(?:[-/]\d{4})?\b")
_AMBIGUOUS_COHORT_RE = re.compile(r"\b(?:k|khoa)\s*0*\d{2}\b", flags=re.IGNORECASE)
_AMBIGUOUS_SEMESTER_RE = re.compile(r"\b(?:hoc ky|hk)\s*[12]\b", flags=re.IGNORECASE)
_AMBIGUOUS_ROUND_RE = re.compile(r"\b(?:dot|lan)\s*\d+\b", flags=re.IGNORECASE)
_SOURCE_CITATION_BLOCK_RE = re.compile(
    r"\n+(?:-{3,}\s*)?(?:📚\s*)?(?:Nguồn tham khảo|References)\s*:\s*(?:\n\s*[-*]\s+\S.*)+\s*$",
    flags=re.IGNORECASE,
)
_POLICY_TIMEFRAME_MARKERS = (
    "học phí",
    "học bổng",
    "bhyt",
    "bảo hiểm",
)
_PROGRAM_SCOPE_MARKERS = (
    "chương trình",
    "ctdt",
    "tín chỉ",
    "sổ tay",
)
_GRADUATION_ROUND_MARKERS = (
    "tốt nghiệp",
    "xét tốt nghiệp",
)
_SCHEDULE_MARKERS = (
    "đăng ký học",
    "đăng ký tín chỉ",
    "lịch học",
    "lịch thi",
)
_NORMALIZED_POLICY_TIMEFRAME_MARKERS = tuple(normalize_scope_text(marker) for marker in _POLICY_TIMEFRAME_MARKERS)
_NORMALIZED_PROGRAM_SCOPE_MARKERS = tuple(normalize_scope_text(marker) for marker in _PROGRAM_SCOPE_MARKERS)
_NORMALIZED_GRADUATION_ROUND_MARKERS = tuple(normalize_scope_text(marker) for marker in _GRADUATION_ROUND_MARKERS)
_NORMALIZED_SCHEDULE_MARKERS = tuple(normalize_scope_text(marker) for marker in _SCHEDULE_MARKERS)
_FALLBACK_PRIMARY_REPLY = {
    "en": (
        "I could not find relevant information in the current Knowledge Base. "
        "Please clarify the question or add a concrete discriminator such as academic year, cohort, semester, or round."
    ),
    "vi": (
        "Mình chưa tìm thấy thông tin phù hợp trong Knowledge Base hiện tại. "
        "Bạn có thể nói rõ hơn câu hỏi hoặc nêu thêm mốc như năm học, khóa, học kỳ hay đợt áp dụng không?"
    ),
}
_STUDENT_HANDBOOK_NO_INFO_REPLY = {
    "en": "I could not find this information in the student handbook.",
    "vi": "Không tìm thấy thông tin này trong sổ tay sinh viên.",
}
_WEB_SEARCH_NO_INFO_REPLY = {
    "en": "I could not retrieve current information from ICTU web sources right now. Please try again later.",
    "vi": "Mình chưa lấy được thông tin mới từ các nguồn web ICTU lúc này. Bạn vui lòng thử lại sau.",
}


def route_rag_tool(message: str) -> tuple[str, str]:
    return route_rag_tool_via_orchestrator(message)


def retrieve_tool_context(
    *,
    message: str,
    session_id: str,
    tool_name: str,
    route_name: str,
) -> RAGResult:
    return retrieve_rag_context(
        message=message,
        session_id=session_id,
        route_name=route_name,
        rag_tool=tool_name,
    )


def retrieve_fallback_context(*, message: str, session_id: str, route_name: str) -> RAGResult:
    return retrieve_rag_context(
        message=message,
        session_id=session_id,
        route_name=route_name,
        rag_tool="general_ictu_rag",
    )


def retrieve_general_context(
    *,
    message: str,
    session_id: str,
    route_name: str,
    tool_name: str | None = None,
) -> RAGResult:
    return retrieve_rag_context(
        message=message,
        session_id=session_id,
        route_name=route_name,
        rag_tool=tool_name,
    )


def _log_step(step: str, state: ChatGraphState, **payload: object) -> None:
    session_id = state.get("session_id", "default")
    debug_payload = {
        "original_question": state.get("original_question"),
        "rewritten_question": state.get("rewritten_question"),
        "detected_intent": state.get("detected_intent"),
        "scope_result": state.get("scope_result"),
        "retrieval_query": state.get("retrieval_query"),
        "answer_model": state.get("llm_model"),
    }
    safe_payload = ", ".join(
        f"{key}={value}"
        for key, value in {**debug_payload, **payload}.items()
        if value not in (None, "", [])
    )
    logger.info("[chat_agent] step=%s session=%s %s", step, session_id, safe_payload)


def _normalize_input(state: ChatGraphState) -> ChatGraphState:
    original_question = (state.get("message") or "").strip()
    session_id = (state.get("session_id") or "default").strip() or "default"
    selected_llm_model = (state.get("selected_llm_model") or "auto").strip() or "auto"
    history = list(state.get("persistent_memory") or [])
    if not any(str(item.get("role") or "").casefold() == "user" for item in history):
        try:
            history = load_chat_history(session_id)
        except Exception as exc:
            logger.warning("[chat_agent] contextual_history_load_failed session=%s error=%s", session_id, exc)

    rewritten_question = rewrite_contextual_question(original_question, history)
    message = rewritten_question or original_question

    state["message"] = message
    state["original_question"] = original_question
    state["rewritten_question"] = message
    state["retrieval_query"] = message
    state["is_follow_up"] = bool(original_question and message != original_question)
    state["session_id"] = session_id
    state["selected_llm_model"] = selected_llm_model
    state["language"] = get_current_language(session_id)
    state["handled"] = False
    state["stop_graph"] = False
    state["needs_clarification"] = False
    state["intent"] = "rag"
    _log_step(
        "normalize_input",
        state,
        message_length=len(message),
        llm_model=selected_llm_model,
        is_follow_up=state["is_follow_up"],
    )

    if not original_question:
        state["response"] = "Bạn hãy nhập câu hỏi để mình hỗ trợ nhé."
        state["llm_model"] = "local:empty_input"
        state["intent"] = "empty_input"
        state["handled"] = True
        state["stop_graph"] = True

    return state


def _classify_intent(state: ChatGraphState) -> ChatGraphState:
    if state.get("handled"):
        return state

    message = state["message"]
    session_id = state["session_id"]
    detected_intent = detect_intent(message)
    looks_like_information_query = "?" in message or len(message.split()) >= 5
    if detected_intent in {"greeting", "thanks", "chitchat"} and looks_like_information_query:
        detected_intent = None

    source_years = (
        get_last_retrieval_years(session_id, state.get("persistent_memory", []))
        if is_source_year_follow_up(state.get("original_question") or message)
        else []
    )
    if source_years:
        if len(source_years) == 1:
            state["response"] = f"Nội dung vừa trả lời được truy xuất từ tài liệu năm học **{source_years[0]}**."
        else:
            state["response"] = (
                "Nội dung vừa trả lời được đối chiếu từ các tài liệu năm học: "
                + ", ".join(f"**{year}**" for year in source_years)
                + "."
            )
        state["handled"] = True
        state["mode"] = "retrieval_memory"
        state["intent"] = "source_year_follow_up"
        state["llm_model"] = "local:retrieval_memory"
    elif contains_swear(message):
        state["response"] = get_swear_response()
        state["handled"] = True
        state["mode"] = "guardrail"
        state["intent"] = "moderation"
        state["llm_model"] = "local:moderation"
    elif detected_intent in {"introduction", "thanks", "goodbye", "chitchat", "greeting"}:
        if detected_intent == "greeting":
            state["response"] = get_quick_response(message, target_lang=get_current_language(session_id))
            state["llm_model"] = "local:quick_reply"
        else:
            state["response"] = get_intent_response(detected_intent)
            state["llm_model"] = "local:intent_reply"
        state["handled"] = True
        state["mode"] = "quick_reply"
        state["intent"] = detected_intent
    else:
        state["intent"] = detected_intent or "rag"

    state["detected_intent"] = state["intent"]
    state["language"] = get_current_language(session_id)
    _log_step("classify_intent", state, intent=state.get("intent"), handled=state.get("handled"))
    return state


def _route_rag_tool_step(state: ChatGraphState) -> ChatGraphState:
    if state.get("handled"):
        return state

    rag_tool, rag_route = route_rag_tool(state["message"])
    state["rag_tool"] = rag_tool
    state["rag_route"] = rag_route
    state["selected_tool"] = rag_tool
    state["routing_reason"], state["confidence"], state["fallback_reason"] = _route_telemetry(
        rag_tool,
        rag_route,
    )
    _log_step(
        "route_rag_tool",
        state,
        selected_tool=rag_tool,
        routing_reason=state["routing_reason"],
        confidence=state["confidence"],
        fallback_reason=state["fallback_reason"],
    )
    return state


def _route_telemetry(tool_name: str, route_name: str) -> tuple[str, float, str]:
    keyword_match = re.search(r"router_keyword_score:(\d+)", route_name)
    llm_match = re.search(r"([01](?:\.\d+)?)$", route_name)
    if keyword_match:
        score = int(keyword_match.group(1))
        reason = f"Keyword router matched {tool_name} with score {score}."
        confidence = min(0.95, 0.5 + score * 0.05)
    elif llm_match and "router_llm" in route_name:
        confidence = max(0.0, min(float(llm_match.group(1)), 1.0))
        reason = f"LLM router selected {tool_name}."
    else:
        confidence = 0.5 if tool_name == "general_ictu_rag" else 0.6
        reason = f"Controlled router selected {tool_name}."

    fallback_reason = ""
    if tool_name == "general_ictu_rag" and (
        "fallback" in route_name or "low_conf" in route_name
    ):
        fallback_reason = "No specialized RAG tool matched the question with sufficient confidence."
    return reason, confidence, fallback_reason


def _apply_rag_result(state: ChatGraphState, rag_result: RAGResult) -> ChatGraphState:
    state["context_text"] = rag_result.context_text
    state["sources"] = rag_result.sources
    state["chunks_used"] = rag_result.chunks_used
    state["target_file"] = rag_result.target_file
    state["mode"] = rag_result.mode
    state["chunks"] = rag_result.chunks
    if rag_result.rag_tool:
        state["rag_tool"] = rag_result.rag_tool
    if rag_result.rag_route:
        state["rag_route"] = rag_result.rag_route
    state["selected_tool"] = rag_result.selected_tool or state.get("selected_tool") or state.get("rag_tool", "")
    if rag_result.routing_reason:
        state["routing_reason"] = rag_result.routing_reason
    if rag_result.confidence is not None:
        state["confidence"] = rag_result.confidence
    if rag_result.fallback_reason:
        state["fallback_reason"] = rag_result.fallback_reason
    if "fallback" in rag_result.mode and not state.get("fallback_reason"):
        state["fallback_reason"] = f"Primary retrieval for {state.get('selected_tool')} returned no usable chunks."
    fusion_methods = {
        str(chunk.metadata.get("fusion_method") or "")
        for chunk in rag_result.chunks
        if chunk.metadata.get("fusion_method")
    }
    state["fusion_method"] = rag_result.fusion_method or (sorted(fusion_methods)[0] if fusion_methods else "")
    state["scope_result"] = "blocked" if rag_result.mode == "ictu_scope_guard" else "allowed"
    return state


def _top_retrieval_debug(state: ChatGraphState, limit: int = 5) -> tuple[list[str], list[object]]:
    top_sources: list[str] = []
    top_scores: list[object] = []
    for chunk in state.get("chunks", [])[:limit]:
        metadata = dict(chunk.metadata or {})
        source = str(metadata.get("source") or metadata.get("path") or "").strip()
        if source:
            top_sources.append(source)
        score = next(
            (
                metadata.get(key)
                for key in ("fusion_score", "score", "hybrid_score", "vector_score", "bm25_score")
                if metadata.get(key) is not None
            ),
            None,
        )
        top_scores.append(score)
    return top_sources, top_scores


def _context_is_missing(state: ChatGraphState) -> bool:
    context_text = str(state.get("context_text", "") or "").strip()
    return (
        state.get("mode") != "ictu_scope_guard"
        and not state.get("sources")
        and not state.get("chunks_used")
        and normalize_scope_text(context_text) in _NORMALIZED_MISSING_CONTEXT_TEXTS
    )


def _clear_unconsumed_sources(state: ChatGraphState) -> None:
    state["sources"] = []
    state["chunks_used"] = 0


def _response_is_no_info(response: str) -> bool:
    return normalize_scope_text(response) in _NORMALIZED_NO_INFO_RESPONSES


def _build_clarification_question(message: str) -> str | None:
    normalized = normalize_scope_text(message)

    asks_policy_timeframe = any(keyword in normalized for keyword in _NORMALIZED_POLICY_TIMEFRAME_MARKERS)
    asks_program_scope = any(keyword in normalized for keyword in _NORMALIZED_PROGRAM_SCOPE_MARKERS)
    asks_graduation_round = any(keyword in normalized for keyword in _NORMALIZED_GRADUATION_ROUND_MARKERS)
    asks_schedule = any(keyword in normalized for keyword in _NORMALIZED_SCHEDULE_MARKERS)

    has_year = bool(_AMBIGUOUS_YEAR_RE.search(message))
    has_cohort = bool(_AMBIGUOUS_COHORT_RE.search(normalized))
    has_semester = bool(_AMBIGUOUS_SEMESTER_RE.search(normalized))
    has_round = bool(_AMBIGUOUS_ROUND_RE.search(normalized))

    if asks_policy_timeframe and not (has_year or has_round):
        return "Bạn muốn hỏi cho năm học hoặc đợt nào để mình tra đúng tài liệu?"
    if asks_program_scope and not (has_year or has_cohort):
        return "Bạn muốn tra cho khóa hoặc năm học nào để mình lấy đúng tài liệu?"
    if asks_graduation_round and not (has_year or has_round):
        return "Bạn muốn hỏi cho đợt hoặc năm học nào để mình trả lời chính xác?"
    if asks_schedule and not (has_year or has_semester):
        return "Bạn muốn tra cho học kỳ hoặc năm học nào?"
    return None


def _retrieve_context_for_tool(state: ChatGraphState, tool_name: str) -> ChatGraphState:
    if state.get("handled"):
        return state

    route_name = state.get("rag_route", "general_rag")
    if tool_name == "general_ictu_rag":
        result = retrieve_general_context(
            message=state["message"],
            session_id=state["session_id"],
            route_name=route_name,
            tool_name=tool_name,
        )
    else:
        result = retrieve_tool_context(
            message=state["message"],
            session_id=state["session_id"],
            tool_name=tool_name,
            route_name=route_name,
        )

    state = _apply_rag_result(state, result)
    state["retrieval_query"] = state["message"]
    clarification_question = _build_clarification_question(state["message"])
    if clarification_question and (_context_is_missing(state) or len(state.get("sources", [])) > 1):
        state["needs_clarification"] = True
        state["clarification_question"] = clarification_question

    top_sources, top_scores = _top_retrieval_debug(state)
    _log_step(
        "retrieve_context",
        state,
        mode=state.get("mode"),
        sources=len(state.get("sources", [])),
        chunks_used=state.get("chunks_used", 0),
        needs_clarification=state.get("needs_clarification"),
        top_sources=top_sources,
        top_scores=top_scores,
    )
    return state


def _retrieve_student_handbook_node(state: ChatGraphState) -> ChatGraphState:
    return _retrieve_context_for_tool(state, "student_handbook_rag")


def _retrieve_academic_policy_node(state: ChatGraphState) -> ChatGraphState:
    return _retrieve_context_for_tool(state, "academic_policy_rag")


def _retrieve_student_faq_node(state: ChatGraphState) -> ChatGraphState:
    return _retrieve_context_for_tool(state, "student_faq_rag")


def _retrieve_general_ictu_node(state: ChatGraphState) -> ChatGraphState:
    return _retrieve_context_for_tool(state, "general_ictu_rag")


def _fallback_kb_reply(state: ChatGraphState) -> str:
    current_language = get_current_language(state.get("session_id", "default"))
    if state.get("rag_tool") == "student_handbook_rag" and not state.get("needs_clarification"):
        primary_message = _STUDENT_HANDBOOK_NO_INFO_REPLY.get(
            current_language,
            _STUDENT_HANDBOOK_NO_INFO_REPLY["vi"],
        )
    else:
        primary_message = _FALLBACK_PRIMARY_REPLY.get(
            current_language,
            _FALLBACK_PRIMARY_REPLY["vi"],
        )
    clarification_question = ""
    if state.get("needs_clarification") and state.get("clarification_question"):
        primary_message = ""
        clarification_question = state["clarification_question"]
    return render_prompt(
        "fallback_prompt.md",
        primary_message=primary_message,
        clarification_question=clarification_question,
    )


def _append_source_citations(response: str, state: ChatGraphState) -> str:
    """Keep answer text clean; clients render structured sources separately."""
    if not response:
        return response
    return _SOURCE_CITATION_BLOCK_RE.sub("", response).rstrip()


def _generate_answer(state: ChatGraphState) -> ChatGraphState:
    if state.get("handled") and state.get("response"):
        _log_step("generate_answer", state, mode=state.get("mode", "handled_local"))
        return state

    if state.get("mode") == "ictu_scope_guard":
        state["response"] = state.get("context_text", "")
        state["llm_model"] = "local:ictu_scope_guard"
        state["language"] = get_current_language(state["session_id"])
        _log_step("generate_answer", state, mode="ictu_scope_guard")
        return state

    if state.get("needs_clarification"):
        state["response"] = _fallback_kb_reply(state)
        state["llm_model"] = "local:clarification"
        state["language"] = get_current_language(state["session_id"])
        _clear_unconsumed_sources(state)
        _log_step("generate_answer", state, mode="clarification")
        return state

    if state.get("mode") == "web_search_empty":
        current_language = get_current_language(state["session_id"])
        state["response"] = _WEB_SEARCH_NO_INFO_REPLY.get(
            current_language,
            _WEB_SEARCH_NO_INFO_REPLY["vi"],
        )
        state["llm_model"] = "local:web_search_empty"
        state["language"] = current_language
        _log_step("generate_answer", state, mode="web_search_empty")
        return state

    if _context_is_missing(state):
        state["response"] = _fallback_kb_reply(state)
        state["llm_model"] = "local:knowledge_base_fallback"
        state["language"] = get_current_language(state["session_id"])
        _log_step("generate_answer", state, mode="knowledge_base_fallback")
        return state

    response, llm_model = chat_multilingual(
        user_question=state["message"],
        context_text=state.get("context_text", "Thông tin đang được cập nhật."),
        session_id=state["session_id"],
        rag_tool=state.get("rag_tool"),
        selected_model=state.get("selected_llm_model"),
        memory_messages=state.get("persistent_memory", []),
    )
    response = _append_source_citations(response, state)
    if _response_is_no_info(response):
        _clear_unconsumed_sources(state)
    state["response"] = response
    state["llm_model"] = llm_model
    state["language"] = get_current_language(state["session_id"])
    _log_step("generate_answer", state, llm_model=llm_model, mode=state.get("mode"))
    return state


def _build_auto_approve_entry_id(session_id: str, answer_row_id: int) -> str:
    """Build entry_id matching knowledge_base_service._build_chat_entry_id format."""
    return f"chat::{session_id}::{answer_row_id}"


def _is_source_grounded_review_candidate(state: ChatGraphState) -> bool:
    if not state.get("response") or not state.get("message"):
        return False

    intent = str(state.get("intent", "") or "")
    if intent in {"moderation", "empty_input"}:
        return False

    mode = str(state.get("mode", "") or "")
    blocked_modes = (
        "fallback",
        "clarification",
        "guardrail",
        "quick_reply",
        "web_search",
    )
    if any(marker in mode for marker in blocked_modes):
        return False

    return bool(state.get("sources")) and int(state.get("chunks_used") or 0) > 0


def _should_auto_approve(state: ChatGraphState) -> bool:
    """Return True only for explicitly enabled, source-grounded auto approval."""
    return settings.AUTO_APPROVE_CHAT_QA and _is_source_grounded_review_candidate(state)


def _save_history(state: ChatGraphState) -> ChatGraphState:
    message = state.get("original_question") or state.get("message", "")
    rewritten_question = state.get("rewritten_question") or message
    response = state.get("response", "")
    session_id = state.get("session_id", "default")

    user_row_id = 0
    bot_row_id = 0
    if message:
        user_row_id = save_message(
            "user",
            message,
            session_id=session_id,
            owner_username=str(state.get("owner_username") or ""),
            owner_role=str(state.get("owner_role") or ""),
            original_question=message,
            rewritten_question=rewritten_question,
        )
    if response:
        bot_row_id = save_message(
            "bot",
            response,
            session_id=session_id,
            owner_username=str(state.get("owner_username") or ""),
            owner_role=str(state.get("owner_role") or ""),
        )

    if response and "web_search" in str(state.get("mode", "")):
        state["web_kb_status"] = save_web_search_answer(
            question=message,
            answer=response,
            chunks=state.get("chunks", []),
            rag_tool=state.get("rag_tool"),
            rag_route=state.get("rag_route"),
            llm_model=state.get("llm_model"),
        )

    if state.get("chunks"):
        append_retrieval_memory(
            session_id,
            query=state.get("retrieval_query") or rewritten_question,
            original_question=message,
            rewritten_question=rewritten_question,
            sources=state.get("sources", []),
            retrieved_ids=[
                chunk.metadata.get("path", chunk.metadata.get("id", ""))
                for chunk in state.get("chunks", [])[:25]
            ],
            rag_tool=state.get("rag_tool"),
        )

    if bot_row_id and user_row_id and _is_source_grounded_review_candidate(state):
        entry_id = _build_auto_approve_entry_id(session_id, bot_row_id)
        state["qa_review_entry_id"] = entry_id
        if _should_auto_approve(state):
            try:
                from services.content.knowledge_base_service import approve_chat_entry
                result = approve_chat_entry(entry_id=entry_id, tool_name=state.get("rag_tool") or DEFAULT_RAG_TOOL)
                state["auto_approved_kb"] = True
                state["qa_review_status"] = "approved"
                logger.info(
                    "[chat_agent] auto_approve_kb entry_id=%s indexed=%s",
                    entry_id,
                    result.get("indexed"),
                )
            except Exception as exc:
                state["auto_approved_kb"] = False
                state["qa_review_status"] = "pending"
                logger.warning("[chat_agent] auto_approve_kb failed: %s", exc)
        else:
            try:
                from services.content.knowledge_base_service import mark_chat_entry_pending
                mark_chat_entry_pending(
                    entry_id=entry_id,
                    tool_name=state.get("rag_tool") or DEFAULT_RAG_TOOL,
                    reason="source_grounded_answer",
                )
                state["auto_approved_kb"] = False
                state["qa_review_status"] = "pending"
            except Exception as exc:
                state["qa_review_status"] = "untracked"
                logger.warning("[chat_agent] queue_review failed: %s", exc)

    state["language"] = get_current_language(session_id)
    _log_step("save_history", state, saved_response=bool(response))
    return state


def get_chat_graph_engine() -> str:
    return _build_chat_graph().engine


def _pass_through_step(state: ChatGraphState) -> ChatGraphState:
    return state


@lru_cache(maxsize=1)
def _build_chat_graph() -> RAGChatGraph:
    tool_nodes = {
        "student_handbook_rag": _retrieve_student_handbook_node,
        "academic_policy_rag": _retrieve_academic_policy_node,
        "student_faq_rag": _retrieve_student_faq_node,
        "general_ictu_rag": _retrieve_general_ictu_node,
    }
    return RAGChatGraph(
        normalize=_normalize_input,
        persist_user=_classify_intent,
        guardrails=_pass_through_step,
        route_rag=_route_rag_tool_step,
        tool_nodes=tool_nodes,
        default_tool=DEFAULT_RAG_TOOL,
        generate=_generate_answer,
        finalize=_save_history,
    )


async def process_chat_message(
    message: str,
    session_id: str = "default",
    llm_model: str = "auto",
    owner_username: str = "",
    owner_role: str = "",
) -> dict:
    started_at = time.perf_counter()
    memory_store = get_default_memory_store()
    memory_key = stable_session_id(
        user_id=str(owner_username or "").strip().casefold() or None,
        anonymous_id=session_id,
    )
    try:
        persistent_memory = await memory_store.load(memory_key)
    except Exception as exc:
        logger.warning("[chat_agent] persistent_memory_load_failed session=%s error=%s", session_id, exc)
        persistent_memory = []

    state: ChatGraphState = {
        "message": message,
        "session_id": session_id,
        "selected_llm_model": llm_model,
        "persistent_memory": persistent_memory,
        "owner_username": owner_username,
        "owner_role": owner_role,
    }
    state = _build_chat_graph().invoke(state)
    response_time_ms = int((time.perf_counter() - started_at) * 1000)
    state["response_time_ms"] = response_time_ms
    try:
        response = str(state.get("response") or "")
        if message and response:
            memory_question = str(state.get("rewritten_question") or message)
            updated_memory = [
                *persistent_memory,
                {"role": "user", "content": memory_question},
                {
                    "role": "model",
                    "content": response,
                    "sources": list(state.get("sources") or []),
                },
            ][-40:]
            await memory_store.save(memory_key, updated_memory)
    except Exception as exc:
        logger.warning("[chat_agent] persistent_memory_save_failed session=%s error=%s", session_id, exc)

    try:
        sources = state.get("sources", [])
        await get_eval_tracker().log_response(
            query=state.get("retrieval_query") or state.get("rewritten_question") or message,
            answer_length=len(str(state.get("response") or "")),
            sources_returned=len(sources),
            latency_ms=response_time_ms,
            has_sources=bool(sources),
            user_thumbs_up=None,
        )
    except Exception as exc:
        logger.warning("[chat_agent] eval_log_failed session=%s error=%s", session_id, exc)

    return build_chat_response_payload(state, response_time_ms=response_time_ms)
