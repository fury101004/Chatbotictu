from __future__ import annotations

from services.ictu_scope_service import normalize_scope_text


DEFAULT_CONTEXT_TEXT = "ThĂ´ng tin Ä‘ang Ä‘Æ°á»£c cáº­p nháº­t."
_UNTITLED_SENTINELS = ("KhĂ´ng cĂ³ tiĂªu Ä‘á»",)
_NORMALIZED_UNTITLED_SENTINELS = tuple(normalize_scope_text(marker) for marker in _UNTITLED_SENTINELS)


def build_context_entry(*, title: str, text: str, context_entry: str = "") -> str:
    if context_entry.strip():
        return context_entry.strip()

    clean_text = text.strip().replace("\n", " ")[:2000]
    clean_title = title.strip()
    if clean_title and normalize_scope_text(clean_title) not in _NORMALIZED_UNTITLED_SENTINELS:
        return f"[{clean_title}]\n{clean_text}"
    return clean_text


def build_context_text(parts: list[str]) -> str:
    filtered_parts = [part.strip() for part in parts if str(part or "").strip()]
    return "\n\n".join(filtered_parts) if filtered_parts else DEFAULT_CONTEXT_TEXT
