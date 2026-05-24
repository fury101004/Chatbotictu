from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, TypedDict

from pydantic import BaseModel, Field, field_validator

from config.settings import settings


MAX_CHAT_MESSAGE_CHARS = settings.MAX_CHAT_MESSAGE_CHARS
MAX_CHAT_SESSION_ID_CHARS = settings.MAX_CHAT_SESSION_ID_CHARS
MAX_CHAT_MODEL_CHARS = 120


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_CHAT_MESSAGE_CHARS)
    session_id: str = Field(default="default", max_length=MAX_CHAT_SESSION_ID_CHARS)
    llm_model: Optional[str] = Field(default=None, max_length=MAX_CHAT_MODEL_CHARS)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError("message must not be blank")
        return cleaned

    @field_validator("session_id")
    @classmethod
    def normalize_session_id(cls, value: str) -> str:
        cleaned = str(value or "").strip()
        return cleaned or "default"


class ChatResponse(BaseModel):
    response: str
    sources: Optional[list[str]] = None
    source_details: Optional[list[dict[str, str]]] = None
    mode: Optional[str] = None
    chunks_used: Optional[int] = None
    language: Optional[str] = None
    rag_tool: Optional[str] = None
    rag_route: Optional[str] = None
    llm_model: Optional[str] = None
    intent: Optional[str] = None
    needs_clarification: Optional[bool] = None
    response_time_ms: Optional[int] = None
    web_kb_status: Optional[dict[str, Any]] = None
    qa_review_status: Optional[str] = None
    qa_review_entry_id: Optional[str] = None
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
    intent: str
    needs_clarification: bool
    clarification_question: str
    target_file: Optional[str]
    context_text: str
    sources: list[str]
    source_details: list[dict[str, str]]
    chunks_used: int
    chunks: list[RetrievedChunk]
    rag_tool: str
    rag_route: str
    llm_model: str
    selected_llm_model: str
    persistent_memory: list[dict[str, str]]
    web_kb_status: dict[str, Any]
    qa_review_status: str
    qa_review_entry_id: str
    response_time_ms: int
