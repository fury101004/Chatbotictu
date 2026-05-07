from __future__ import annotations

from typing import Optional

from models.chat import RAGResult
from services.rag.rag_types import RetrievalFlowPlan
from services.rag.rag_service import (
    retrieve_fallback_context,
    retrieve_general_context,
    retrieve_tool_context,
    route_rag_tool,
    route_retrieval_flow,
)


def route_tool(message: str) -> tuple[str, str]:
    return route_rag_tool(message)


def route_flow(message: str, rag_tool: Optional[str] = None) -> RetrievalFlowPlan:
    return route_retrieval_flow(message, rag_tool)


def retrieve_context(
    *,
    message: str,
    session_id: str,
    route_name: str,
    rag_tool: Optional[str],
    retrieval_plan: Optional[RetrievalFlowPlan] = None,
) -> RAGResult:
    if rag_tool == "student_handbook_rag":
        return retrieve_tool_context(
            message=message,
            session_id=session_id,
            tool_name="student_handbook_rag",
            route_name=route_name,
            retrieval_plan=retrieval_plan,
        )
    if rag_tool == "school_policy_rag":
        return retrieve_tool_context(
            message=message,
            session_id=session_id,
            tool_name="school_policy_rag",
            route_name=route_name,
            retrieval_plan=retrieval_plan,
        )
    if rag_tool == "student_faq_rag":
        return retrieve_tool_context(
            message=message,
            session_id=session_id,
            tool_name="student_faq_rag",
            route_name=route_name,
            retrieval_plan=retrieval_plan,
        )
    if rag_tool == "fallback_rag":
        return retrieve_fallback_context(
            message=message,
            session_id=session_id,
            route_name=route_name,
            retrieval_plan=retrieval_plan,
        )
    return retrieve_general_context(
        message=message,
        session_id=session_id,
        route_name=route_name,
        tool_name=rag_tool,
        retrieval_plan=retrieval_plan,
    )

