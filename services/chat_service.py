from __future__ import annotations

from datetime import datetime

from config.rag_tools import DEFAULT_RAG_TOOL, FALLBACK_RAG_NODE
from models.chat import ChatGraphState, RAGResult
from services.graph_service import RAGChatGraph
from services.rag_service import (
    retrieve_fallback_context,
    retrieve_general_context,
    retrieve_tool_context,
    route_rag_tool,
)
from services.moderation_service import contains_swear, get_swear_response
from config.db import save_message
from services.multilingual_service import chat_multilingual, get_current_language
from services.quick_reply_service import get_quick_response
from services.vector_store_service import SESSION_MEMORY



def _normalize_input(state: ChatGraphState) -> ChatGraphState:
    message = (state.get("message") or "").strip()
    session_id = state.get("session_id") or "default"
    state["message"] = message
    state["session_id"] = session_id
    state["language"] = get_current_language(session_id)

    if not message:
        state["response"] = "Ban gui gi do di chu"
        state["handled"] = True
        state["stop_graph"] = True

    return state



def _persist_user_message(state: ChatGraphState) -> ChatGraphState:
    save_message("user", state["message"], session_id=state["session_id"])
    return state



def _handle_guardrails(state: ChatGraphState) -> ChatGraphState:
    message = state["message"]
    session_id = state["session_id"]
    message_lower = message.lower()

    if contains_swear(message):
        state["response"] = get_swear_response()
        state["handled"] = True
        state["mode"] = "guardrail"
        return state

    if len(message) <= 12 and not message.endswith("?"):
        greetings = {
            "hi",
            "hello",
            "hey",
            "yo",
            "chao",
            "alo",
            "he lo",
            "good morning",
            "good evening",
        }
        if any(greeting in message_lower for greeting in greetings):
            state["response"] = get_quick_response(message, target_lang=get_current_language(session_id))
            state["handled"] = True
            state["mode"] = "quick_reply"

    state["language"] = get_current_language(session_id)
    return state



def _route_rag(state: ChatGraphState) -> ChatGraphState:
    rag_tool, rag_route = route_rag_tool(state["message"])
    state["rag_tool"] = rag_tool
    state["rag_route"] = rag_route
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



def _retrieve_handbook_rag(state: ChatGraphState) -> ChatGraphState:
    result = retrieve_tool_context(
        message=state["message"],
        session_id=state["session_id"],
        tool_name="student_handbook_rag",
        route_name=state.get("rag_route", "router_handbook"),
    )
    return _apply_rag_result(state, result)



def _retrieve_policy_rag(state: ChatGraphState) -> ChatGraphState:
    result = retrieve_tool_context(
        message=state["message"],
        session_id=state["session_id"],
        tool_name="school_policy_rag",
        route_name=state.get("rag_route", "router_policy"),
    )
    return _apply_rag_result(state, result)



def _retrieve_faq_rag(state: ChatGraphState) -> ChatGraphState:
    result = retrieve_tool_context(
        message=state["message"],
        session_id=state["session_id"],
        tool_name="student_faq_rag",
        route_name=state.get("rag_route", "router_faq"),
    )
    return _apply_rag_result(state, result)



def _retrieve_fallback_rag(state: ChatGraphState) -> ChatGraphState:
    result = retrieve_fallback_context(
        message=state["message"],
        session_id=state["session_id"],
        route_name=state.get("rag_route", "router_fallback"),
    )
    return _apply_rag_result(state, result)



def _retrieve_general_rag(state: ChatGraphState) -> ChatGraphState:
    result = retrieve_general_context(
        message=state["message"],
        session_id=state["session_id"],
        route_name=state.get("rag_route", "general_rag"),
        tool_name=state.get("rag_tool"),
    )
    return _apply_rag_result(state, result)



def _generate_response(state: ChatGraphState) -> ChatGraphState:
    response = chat_multilingual(
        user_question=state["message"],
        context_text=state.get("context_text", "Thong tin dang duoc cap nhat."),
        session_id=state["session_id"],
    )
    state["response"] = response
    state["language"] = get_current_language(state["session_id"])
    return state



def _finalize(state: ChatGraphState) -> ChatGraphState:
    response = state.get("response", "")
    session_id = state["session_id"]

    if response:
        save_message("bot", response, session_id=session_id)

    if state.get("chunks"):
        SESSION_MEMORY[session_id].append(
            {
                "query": state["message"],
                "timestamp": datetime.now().isoformat(),
                "sources": state.get("sources", []),
                "retrieved_ids": [chunk.metadata.get("path", chunk.metadata.get("id", "")) for chunk in state.get("chunks", [])[:25]],
                "rag_tool": state.get("rag_tool"),
            }
        )

    state["language"] = get_current_language(session_id)
    return state


_CHAT_GRAPH = RAGChatGraph(
    normalize=_normalize_input,
    persist_user=_persist_user_message,
    guardrails=_handle_guardrails,
    route_rag=_route_rag,
    tool_nodes={
        "student_handbook_rag": _retrieve_handbook_rag,
        "school_policy_rag": _retrieve_policy_rag,
        "student_faq_rag": _retrieve_faq_rag,
        FALLBACK_RAG_NODE: _retrieve_fallback_rag,
    },
    default_tool=DEFAULT_RAG_TOOL,
    retrieve=_retrieve_general_rag,
    generate=_generate_response,
    finalize=_finalize,
)



def get_chat_graph_engine() -> str:
    return _CHAT_GRAPH.engine


async def process_chat_message(message: str, session_id: str = "default") -> dict:
    state = _CHAT_GRAPH.invoke({"message": message, "session_id": session_id})
    result = {
        "response": state.get("response", ""),
        "language": state.get("language"),
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

    return result

