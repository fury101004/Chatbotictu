from __future__ import annotations

from typing import Optional

from langchain_core.prompts import ChatPromptTemplate

from config.rag_tools import FALLBACK_RAG_NODE, RAG_TOOL_PROFILES
from shared.prompt_loader import render_prompt


_RAW_TEXT_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("human", "{prompt}"),
    ]
)


def _build_rag_router_prompt(message: str) -> str:
    tool_descriptions = "\n".join(
        f"- {tool_name}: {profile.get('description', profile.get('label', tool_name))}"
        for tool_name, profile in RAG_TOOL_PROFILES.items()
    )
    return render_prompt(
        "rag_router.md",
        tool_descriptions=tool_descriptions,
        message=message,
    )


def _build_retrieval_flow_prompt(message: str, rag_tool: Optional[str]) -> str:
    tool_descriptions = "\n".join(
        f"- {tool_name}: {profile.get('description', profile.get('label', tool_name))}"
        for tool_name, profile in RAG_TOOL_PROFILES.items()
    )
    current_tool = rag_tool if rag_tool in RAG_TOOL_PROFILES else FALLBACK_RAG_NODE
    return render_prompt(
        "retrieval_flow.md",
        current_tool=current_tool,
        tool_descriptions=tool_descriptions,
        message=message,
    )
