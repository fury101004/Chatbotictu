from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

try:  # Lazy enough for startup: model weights are not loaded until class instantiation.
    from sentence_transformers import CrossEncoder
except Exception:  # pragma: no cover - depends on optional runtime environment.
    CrossEncoder = None  # type: ignore[assignment]


DEFAULT_CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class CrossEncoderReranker:
    def __init__(self, model_name: str = DEFAULT_CROSS_ENCODER_MODEL, top_k: int = 5) -> None:
        self.model_name = model_name
        self.top_k = max(1, int(top_k))
        self._model: Any = None
        self._load_attempted = False
        self._disabled = False

    def _get_model(self) -> Any:
        if self._disabled:
            return None
        if self._load_attempted:
            return self._model
        self._load_attempted = True

        if CrossEncoder is None:
            self._disabled = True
            logger.warning("sentence-transformers CrossEncoder is unavailable; reranker disabled.")
            return None

        try:
            self._model = CrossEncoder(self.model_name, local_files_only=True)
        except Exception as exc:
            self._disabled = True
            logger.warning("Failed to load cross-encoder reranker %s: %s", self.model_name, exc)
            return None
        return self._model

    def rank(self, query: str, documents: list[str]) -> list[int]:
        clean_query = str(query or "").strip()
        if not clean_query or len(documents) <= 1:
            return list(range(min(self.top_k, len(documents))))

        model = self._get_model()
        if model is None:
            return list(range(min(self.top_k, len(documents))))

        try:
            pairs = [(clean_query, str(document or "")) for document in documents]
            scores = list(model.predict(pairs))
            ranked = sorted(enumerate(scores), key=lambda item: float(item[1]), reverse=True)
            return [index for index, _score in ranked[: self.top_k]]
        except Exception as exc:
            logger.warning("Cross-encoder reranking failed; using original retrieval order: %s", exc)
            return list(range(min(self.top_k, len(documents))))

    def rerank(self, query: str, documents: list[str]) -> list[str]:
        return [documents[index] for index in self.rank(query, documents)]


@lru_cache(maxsize=1)
def get_default_reranker() -> CrossEncoderReranker:
    return CrossEncoderReranker(DEFAULT_CROSS_ENCODER_MODEL, top_k=5)


def rerank_langchain_documents(
    query: str,
    documents: list[Document],
    *,
    top_k: int | None = None,
    reranker: CrossEncoderReranker | None = None,
) -> list[Document]:
    if not documents:
        return []

    rule_documents = [
        document
        for document in documents
        if str(document.metadata.get("source", "")) == "BOT_RULE"
    ]
    candidate_documents = [
        document
        for document in documents
        if str(document.metadata.get("source", "")) != "BOT_RULE"
    ]
    for pre_rank, document in enumerate(candidate_documents, start=1):
        document.metadata.setdefault("pre_rerank_rank", pre_rank)

    selected_reranker = reranker or get_default_reranker()
    original_top_k = selected_reranker.top_k
    if top_k is not None:
        selected_reranker.top_k = max(1, int(top_k))
    try:
        indexes = selected_reranker.rank(query, [document.page_content for document in candidate_documents])
    finally:
        selected_reranker.top_k = original_top_k

    reranked = [candidate_documents[index] for index in indexes]
    for post_rank, document in enumerate(reranked, start=1):
        document.metadata["post_rerank_rank"] = post_rank
    return [*rule_documents, *reranked]
