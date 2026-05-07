from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Optional

from config.rag_tools import DEFAULT_RAG_TOOL, UPLOAD_SOURCE_PREFIX, detect_tool_from_path, is_valid_rag_tool
from config.settings import settings


def infer_vector_tool_name(source: str, raw_tool_name: Optional[str]) -> Optional[str]:
    if is_valid_rag_tool(raw_tool_name):
        return str(raw_tool_name)

    normalized_source = str(source or "").replace("\\", "/")
    if not normalized_source or normalized_source == "BOT_RULE":
        return None

    path_parts = PurePosixPath(normalized_source).parts
    if len(path_parts) >= 3 and path_parts[0] == UPLOAD_SOURCE_PREFIX and is_valid_rag_tool(path_parts[1]):
        return path_parts[1]

    inferred_tool = detect_tool_from_path(settings.QA_CORPUS_ROOT / Path(normalized_source))
    if is_valid_rag_tool(inferred_tool):
        return str(inferred_tool)

    return DEFAULT_RAG_TOOL


def display_vector_source(source: str, *, unknown_label: str = "unknown.md") -> str:
    normalized_source = str(source or "").replace("\\", "/")
    if not normalized_source:
        return unknown_label
    if normalized_source == "BOT_RULE":
        return "BOT_RULE"
    return PurePosixPath(normalized_source).name or normalized_source
