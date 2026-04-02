"""Document reranking helpers."""

from __future__ import annotations

from functools import lru_cache
import re
from typing import Any, List, Sequence
import unicodedata

from app.core.config import ENABLE_NEURAL_RERANKER, NEURAL_RERANKER_MODEL

STOPWORDS = {
    "va",
    "la",
    "de",
    "gi",
    "khi",
    "nao",
    "o",
    "dau",
    "nhu",
    "the",
    "co",
    "can",
    "em",
    "toi",
    "cho",
    "ve",
    "duoc",
    "voi",
    "mot",
    "nhung",
    "nay",
}


@lru_cache(maxsize=1)
def _get_model() -> Any:
    if not ENABLE_NEURAL_RERANKER:
        return None

    try:
        from sentence_transformers import CrossEncoder
    except Exception:
        return None

    try:
        return CrossEncoder(NEURAL_RERANKER_MODEL)
    except Exception:
        return None


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    return re.sub(r"\s+", " ", normalized).strip()


def _tokenize(value: str) -> List[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", _normalize_text(value))
        if token not in STOPWORDS and len(token) > 1
    ]


def _lexical_score(query: str, content: str) -> float:
    query_tokens = _tokenize(query)
    content_tokens = _tokenize(content)

    if not query_tokens or not content_tokens:
        return 0.0

    query_set = set(query_tokens)
    content_set = set(content_tokens)
    overlap = query_set & content_set
    normalized_content = " ".join(content_tokens)
    phrase_bonus = 0.0

    for token in overlap:
        phrase_bonus += 1.0 + (normalized_content.count(token) * 0.05)

    if _normalize_text(query) in normalized_content:
        phrase_bonus += 3.0

    return (len(overlap) / max(len(query_set), 1)) + phrase_bonus


def rerank(query: str, documents: Sequence, top_k: int = 5) -> List:
    if not documents:
        return []

    limited_documents = list(documents)
    pairs = [(query, document.page_content) for document in limited_documents]
    model = _get_model()

    if model is not None:
        try:
            scores = model.predict(pairs)
            ranked_pairs = sorted(
                zip(limited_documents, scores), key=lambda item: item[1], reverse=True
            )
            return [document for document, _ in ranked_pairs[:top_k]]
        except Exception:
            pass

    scored_documents = sorted(
        limited_documents,
        key=lambda document: _lexical_score(query, document.page_content),
        reverse=True,
    )
    return scored_documents[:top_k]
