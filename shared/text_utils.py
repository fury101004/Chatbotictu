from __future__ import annotations

import re
import unicodedata


def normalize_search_text(text: str, *, strip_punctuation: bool = False) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or "").casefold())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = (
        normalized
        .replace("đ", "d")
        .replace("Ä‘", "d")
        .replace("\u00c4\u2018", "d")
        .replace("&", " va ")
    )
    if strip_punctuation:
        normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def tokenize_search_text(text: str) -> list[str]:
    normalized = normalize_search_text(text)
    return [token for token in re.findall(r"[a-z0-9]+", normalized) if len(token) > 1]
