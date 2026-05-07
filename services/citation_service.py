from __future__ import annotations

from typing import Any


def merge_sources(*source_lists: list[str]) -> list[str]:
    merged: list[str] = []
    for source_list in source_lists:
        for source in source_list:
            source_text = str(source or "").strip()
            if source_text and source_text not in merged:
                merged.append(source_text)
    return merged


def sources_from_metadata(metadata: dict[str, Any]) -> list[str]:
    source = str(metadata.get("source", "") or "").strip()
    base_sources = [source] if source and source != "BOT_RULE" else []
    extra_sources = metadata.get("sources")
    if isinstance(extra_sources, list):
        return merge_sources(base_sources, [str(item or "").strip() for item in extra_sources if str(item or "").strip()])
    return base_sources
