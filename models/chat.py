from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, TypedDict

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    llm_model: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    sources: Optional[list[str]] = None
    mode: Optional[str] = None
    chunks_used: Optional[int] = None
    language: Optional[str] = None
    rag_tool: Optional[str] = None
    rag_route: Optional[str] = None
    llm_model: Optional[str] = None
    web_kb_status: Optional[dict[str, Any]] = None
    timestamp: str
    session_id: str


@dataclass(slots=True)
class RetrievedChunk:
    document: str
    metadata: dict[str, Any]


@dataclass(slots=True)
class RAGResult:
    context_text: str
    chunks: list[RetrievedChunk] = field(default_factory=list)
    target_file: Optional[str] = None
    mode: str = "hybrid_search"
    sources: list[str] = field(default_factory=list)
    chunks_used: int = 0
    rag_tool: Optional[str] = None
    rag_route: Optional[str] = None


class ChatGraphState(TypedDict, total=False):
    message: str
    session_id: str
    response: str
    handled: bool
    stop_graph: bool
    mode: str
    language: str
    target_file: Optional[str]
    context_text: str
    sources: list[str]
    chunks_used: int
    chunks: list[RetrievedChunk]
    rag_tool: str
    rag_route: str
    llm_model: str
    selected_llm_model: str
    web_kb_status: dict[str, Any]









