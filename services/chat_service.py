from __future__ import annotations

import logging
import re
import time
from datetime import datetime

from config.db import save_message
from config.rag_tools import DEFAULT_RAG_TOOL, FALLBACK_RAG_NODE
from models.chat import ChatGraphState, RAGResult
from services.intent_service import detect_intent, get_intent_response
from services.ictu_scope_service import normalize_scope_text
from services.moderation_service import contains_swear, get_swear_response
from services.multilingual_service import chat_multilingual, get_current_language
from services.quick_reply_service import get_quick_response
from services.rag_service import (
    retrieve_fallback_context,
    retrieve_general_context,
    retrieve_tool_context,
    route_rag_tool,
)
from services.vector_store_service import SESSION_MEMORY
from services.web_knowledge_service import save_web_search_answer


logger = logging.getLogger("chat_agent")

_MISSING_CONTEXT_TEXTS = (
    "",
    "Thông tin đang được cập nhật.",
    "Thông tin này hiện chưa có trong tài liệu của em.",
)
_NORMALIZED_MISSING_CONTEXT_TEXTS = tuple(normalize_scope_text(marker) for marker in _MISSING_CONTEXT_TEXTS)
_AMBIGUOUS_YEAR_RE = re.compile(r"\b20\d{2}(?:[-/]\d{4})?\b")
_AMBIGUOUS_COHORT_RE = re.compile(r"\b(?:k|khoa)\s*0*\d{2}\b", flags=re.IGNORECASE)
_AMBIGUOUS_SEMESTER_RE = re.compile(r"\b(?:hoc ky|hk)\s*[12]\b", flags=re.IGNORECASE)
_AMBIGUOUS_ROUND_RE = re.compile(r"\b(?:dot|lan)\s*\d+\b", flags=re.IGNORECASE)
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


def _log_step(step: str, state: ChatGraphState, **payload: object) -> None:
    session_id = state.get("session_id", "default")
    safe_payload = ", ".join(f"{key}={value}" for key, value in payload.items())
    logger.info("[chat_agent] step=%s session=%s %s", step, session_id, safe_payload)


def _normalize_input(state: ChatGraphState) -> ChatGraphState:
    message = (state.get("message") or "").strip()
    session_id = (state.get("session_id") or "default").strip() or "default"
    selected_llm_model = (state.get("selected_llm_model") or "auto").strip() or "auto"

    state["message"] = message
    state["session_id"] = session_id
    state["selected_llm_model"] = selected_llm_model
    state["language"] = get_current_language(session_id)
    state["handled"] = False
    state["stop_graph"] = False
    state["needs_clarification"] = False
    state["intent"] = "rag"
    _log_step("normalize_input", state, message_length=len(message), llm_model=selected_llm_model)

    if not message:
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

    if contains_swear(message):
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

    state["language"] = get_current_language(session_id)
    _log_step("classify_intent", state, intent=state.get("intent"), handled=state.get("handled"))
    return state


def _route_rag_tool_step(state: ChatGraphState) -> ChatGraphState:
    if state.get("handled"):
        return state

    rag_tool, rag_route = route_rag_tool(state["message"])
    state["rag_tool"] = rag_tool
    state["rag_route"] = rag_route
    _log_step("route_rag_tool", state, rag_tool=rag_tool, rag_route=rag_route)
    return state


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
    return state


def _context_is_missing(state: ChatGraphState) -> bool:
    context_text = str(state.get("context_text", "") or "").strip()
    return (
        state.get("mode") != "ictu_scope_guard"
        and not state.get("sources")
        and not state.get("chunks_used")
        and normalize_scope_text(context_text) in _NORMALIZED_MISSING_CONTEXT_TEXTS
    )


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


def _retrieve_context(state: ChatGraphState) -> ChatGraphState:
    if state.get("handled"):
        return state

    route_name = state.get("rag_route", "general_rag")
    rag_tool = state.get("rag_tool") or DEFAULT_RAG_TOOL

    if rag_tool == "student_handbook_rag":
        result = retrieve_tool_context(
            message=state["message"],
            session_id=state["session_id"],
            tool_name="student_handbook_rag",
            route_name=route_name,
        )
    elif rag_tool == "school_policy_rag":
        result = retrieve_tool_context(
            message=state["message"],
            session_id=state["session_id"],
            tool_name="school_policy_rag",
            route_name=route_name,
        )
    elif rag_tool == "student_faq_rag":
        result = retrieve_tool_context(
            message=state["message"],
            session_id=state["session_id"],
            tool_name="student_faq_rag",
            route_name=route_name,
        )
    elif rag_tool == FALLBACK_RAG_NODE:
        result = retrieve_fallback_context(
            message=state["message"],
            session_id=state["session_id"],
            route_name=route_name,
        )
    else:
        result = retrieve_general_context(
            message=state["message"],
            session_id=state["session_id"],
            route_name=route_name,
            tool_name=rag_tool,
        )

    state = _apply_rag_result(state, result)
    clarification_question = _build_clarification_question(state["message"])
    if clarification_question and (_context_is_missing(state) or len(state.get("sources", [])) > 1):
        state["needs_clarification"] = True
        state["clarification_question"] = clarification_question

    _log_step(
        "retrieve_context",
        state,
        mode=state.get("mode"),
        sources=len(state.get("sources", [])),
        chunks_used=state.get("chunks_used", 0),
        needs_clarification=state.get("needs_clarification"),
    )
    return state


def _fallback_kb_reply(state: ChatGraphState) -> str:
    if state.get("needs_clarification") and state.get("clarification_question"):
        return state["clarification_question"]
    return (
        "Mình chưa tìm thấy thông tin phù hợp trong Knowledge Base hiện tại. "
        "Bạn có thể nói rõ hơn câu hỏi hoặc nêu thêm mốc như năm học, khóa, học kỳ hay đợt áp dụng không?"
    )


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
        _log_step("generate_answer", state, mode="clarification")
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
    )
    state["response"] = response
    state["llm_model"] = llm_model
    state["language"] = get_current_language(state["session_id"])
    _log_step("generate_answer", state, llm_model=llm_model, mode=state.get("mode"))
    return state


def _save_history(state: ChatGraphState) -> ChatGraphState:
    message = state.get("message", "")
    response = state.get("response", "")
    session_id = state.get("session_id", "default")

    if message:
        save_message("user", message, session_id=session_id)
    if response:
        save_message("bot", response, session_id=session_id)

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
        SESSION_MEMORY[session_id].append(
            {
                "query": message,
                "timestamp": datetime.now().isoformat(),
                "sources": state.get("sources", []),
                "retrieved_ids": [
                    chunk.metadata.get("path", chunk.metadata.get("id", ""))
                    for chunk in state.get("chunks", [])[:25]
                ],
                "rag_tool": state.get("rag_tool"),
            }
        )

    state["language"] = get_current_language(session_id)
    _log_step("save_history", state, saved_response=bool(response))
    return state


def get_chat_graph_engine() -> str:
    return "sequential_agent"


async def process_chat_message(message: str, session_id: str = "default", llm_model: str = "auto") -> dict:
    started_at = time.perf_counter()
    state: ChatGraphState = {
        "message": message,
        "session_id": session_id,
        "selected_llm_model": llm_model,
    }

    for step in (
        _normalize_input,
        _classify_intent,
        _route_rag_tool_step,
        _retrieve_context,
        _generate_answer,
        _save_history,
    ):
        state = step(state)
        if state.get("stop_graph"):
            break

    response_time_ms = int((time.perf_counter() - started_at) * 1000)
    state["response_time_ms"] = response_time_ms
    result = {
        "response": state.get("response", ""),
        "language": state.get("language"),
        "intent": state.get("intent"),
        "needs_clarification": state.get("needs_clarification"),
        "response_time_ms": response_time_ms,
    }

    if state.get("sources") is not None:
        result["sources"] = state.get("sources", [])
    if state.get("mode") is not None:
        result["mode"] = state.get("mode")
    if state.get("chunks_used") is not None:
        result["chunks_used"] = state.get("chunks_used")
    if state.get("rag_tool") is not None:
        result["rag_tool"] = state.get("rag_tool")
    if state.get("rag_route") is not None:
        result["rag_route"] = state.get("rag_route")
    if state.get("llm_model") is not None:
        result["llm_model"] = state.get("llm_model")
    if state.get("web_kb_status") is not None:
        result["web_kb_status"] = state.get("web_kb_status")

    return result
