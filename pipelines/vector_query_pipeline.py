from __future__ import annotations

import re
import time
import unicodedata
from datetime import datetime
from typing import Any, Callable, Optional

from rank_bm25 import BM25Okapi


FUSION_RRF = "rrf"
FUSION_WEIGHTED = "weighted"
SUPPORTED_FUSION_METHODS = frozenset({FUSION_RRF, FUSION_WEIGHTED})


def normalize_bm25_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or "").casefold())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.replace("đ", "d").replace("&", " va ")
    return re.sub(r"\s+", " ", normalized).strip()


def tokenize_bm25_text(text: str) -> list[str]:
    normalized = normalize_bm25_text(text)
    return [token for token in re.findall(r"[a-z0-9]+", normalized) if len(token) > 1]


def rebuild_bm25_index(
    *,
    collection_getter: Callable[[], Any],
    current_bm25: Optional[BM25Okapi],
    current_tokenized: list[list[str]],
    current_ids: list[str],
    current_count: int,
    bm25_factory: Callable[[list[list[str]]], BM25Okapi],
    tokenize_text_fn: Callable[[str], list[str]],
) -> tuple[Optional[BM25Okapi], list[list[str]], list[str], int]:
    collection = collection_getter()
    document_count = collection.count()
    if document_count == current_count and current_bm25 is not None:
        return current_bm25, current_tokenized, current_ids, current_count

    data = collection.get(include=["documents"])
    documents = [str(document or "") for document in data.get("documents", [])]
    ids = [str(doc_id or "") for doc_id in data.get("ids", [])]
    tokenized_documents = [tokenize_text_fn(document) for document in documents]
    bm25_index = bm25_factory(tokenized_documents) if documents else None
    print(f"BM25 rebuilt with {len(documents)} chunks")
    return bm25_index, tokenized_documents, ids, document_count


def normalize_scores(raw_scores: dict[str, float]) -> dict[str, float]:
    if not raw_scores:
        return {}
    minimum = min(raw_scores.values())
    maximum = max(raw_scores.values())
    if maximum <= minimum:
        return {key: 1.0 for key in raw_scores}
    return {
        key: (value - minimum) / (maximum - minimum + 1e-8)
        for key, value in raw_scores.items()
    }


def top_bm25_candidates(
    query: str,
    *,
    bm25_index: Optional[BM25Okapi],
    all_ids: list[str],
    limit: int,
    tokenize_text_fn: Callable[[str], list[str]],
    allowed_ids: Optional[set[str]] = None,
) -> tuple[dict[str, float], list[str]]:
    if bm25_index is None or not all_ids:
        return {}, []

    query_tokens = tokenize_text_fn(query)
    if not query_tokens:
        return {}, []

    bm25_raw = bm25_index.get_scores(query_tokens)
    raw_scores = {
        doc_id: float(bm25_raw[index])
        for index, doc_id in enumerate(all_ids)
        if allowed_ids is None or doc_id in allowed_ids
    }
    ranked_ids = [
        doc_id
        for doc_id, score in sorted(raw_scores.items(), key=lambda item: item[1], reverse=True)
        if score > 0
    ][:limit]
    return normalize_scores(raw_scores), ranked_ids


def reciprocal_rank_fusion(
    rankings: list[list[str]],
    *,
    k: int = 60,
) -> tuple[dict[str, float], list[str]]:
    if k < 1:
        raise ValueError("RRF k must be at least 1")

    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    next_index = 0
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            if doc_id not in first_seen:
                first_seen[doc_id] = next_index
                next_index += 1
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)

    ranked_ids = sorted(scores, key=lambda doc_id: (-scores[doc_id], first_seen[doc_id]))
    return scores, ranked_ids


def weighted_score_fusion(
    candidate_ids: list[str],
    *,
    vector_scores: dict[str, float],
    bm25_scores: dict[str, float],
    alpha: float,
) -> tuple[dict[str, float], list[str]]:
    bounded_alpha = max(0.0, min(float(alpha), 1.0))
    scores = {
        doc_id: (
            bounded_alpha * vector_scores.get(doc_id, 0.0)
            + (1.0 - bounded_alpha) * bm25_scores.get(doc_id, 0.0)
        )
        for doc_id in candidate_ids
    }
    first_seen = {doc_id: index for index, doc_id in enumerate(candidate_ids)}
    ranked_ids = sorted(scores, key=lambda doc_id: (-scores[doc_id], first_seen[doc_id]))
    return scores, ranked_ids


def normalize_fusion_method(value: str) -> str:
    normalized = str(value or "").strip().casefold()
    return normalized if normalized in SUPPORTED_FUSION_METHODS else FUSION_RRF


def run_hybrid_query(
    *,
    collection: Any,
    query: str,
    user_id: str,
    n_results: int,
    alpha: float,
    fusion_method: str,
    rrf_k: int,
    metadata_filter: Optional[dict[str, Any]],
    bm25_index: Optional[BM25Okapi],
    all_ids: list[str],
    tokenize_text_fn: Callable[[str], list[str]],
    bot_rule_id: str,
    session_memory: Any,
    stats: dict[str, Any],
) -> tuple[list[str], list[dict], dict[str, Any]]:
    started_at = time.time()
    stats["total_queries"] += 1

    if collection.count() == 0:
        return [], [], {"session_history": list(session_memory[user_id]), "stats": stats.copy(), "sources": []}

    vector_candidate_limit = max(n_results + 15, n_results * 3)
    bm25_candidate_limit = max(n_results + 10, n_results * 2)
    vector_query_kwargs: dict[str, Any] = {
        "query_texts": [query],
        "n_results": vector_candidate_limit,
        "include": ["documents", "metadatas", "distances"],
    }
    if metadata_filter:
        vector_query_kwargs["where"] = metadata_filter
    vector_results = collection.query(**vector_query_kwargs)

    vector_ids = vector_results["ids"][0]
    vector_distances = vector_results["distances"][0]
    cosine_raw = {doc_id: 1.0 - distance for doc_id, distance in zip(vector_ids, vector_distances)}
    normalized_cosine = normalize_scores(cosine_raw)
    allowed_ids: Optional[set[str]] = None
    if metadata_filter:
        filtered_payload = collection.get(where=metadata_filter, include=["metadatas"])
        allowed_ids = {str(doc_id) for doc_id in filtered_payload.get("ids", [])}

    normalized_bm25, bm25_ids = top_bm25_candidates(
        query,
        bm25_index=bm25_index,
        all_ids=all_ids,
        limit=bm25_candidate_limit,
        tokenize_text_fn=tokenize_text_fn,
        allowed_ids=allowed_ids,
    )

    candidate_ids = list(dict.fromkeys([*vector_ids, *bm25_ids]))
    selected_fusion_method = normalize_fusion_method(fusion_method)
    if selected_fusion_method == FUSION_WEIGHTED:
        fusion_scores, ranked_ids = weighted_score_fusion(
            candidate_ids,
            vector_scores=normalized_cosine,
            bm25_scores=normalized_bm25,
            alpha=alpha,
        )
    else:
        fusion_scores, ranked_ids = reciprocal_rank_fusion(
            [list(vector_ids), list(bm25_ids)],
            k=rrf_k,
        )

    top_ids = list(dict.fromkeys([bot_rule_id, *ranked_ids[: n_results + 5]]))
    payload = collection.get(ids=top_ids, include=["documents", "metadatas"])
    documents = payload["documents"]
    metadatas = payload["metadatas"]
    ids = payload["ids"]
    items_by_id = {
        doc_id: (document, metadata)
        for doc_id, document, metadata in zip(ids, documents, metadatas)
    }

    rule_doc = None
    rule_meta = None
    normal_docs: list[str] = []
    normal_metas: list[dict[str, Any]] = []

    for doc_id in top_ids:
        item = items_by_id.get(doc_id)
        if item is None:
            continue
        document, metadata = item
        metadata = dict(metadata or {})
        if metadata.get("source") == "BOT_RULE" or doc_id == bot_rule_id:
            rule_doc = document
            rule_meta = metadata
            continue

        metadata["fusion_method"] = selected_fusion_method
        metadata["fusion_score"] = round(fusion_scores.get(doc_id, 0.0), 8)
        metadata["hybrid_score"] = metadata["fusion_score"]
        metadata["vector_score"] = round(normalized_cosine.get(doc_id, 0.0), 6)
        metadata["bm25_score"] = round(normalized_bm25.get(doc_id, 0.0), 6)
        metadata["pre_rerank_rank"] = ranked_ids.index(doc_id) + 1
        normal_docs.append(document)
        normal_metas.append(metadata)

    if not rule_doc:
        rule_payload = collection.get(ids=[bot_rule_id], include=["documents", "metadatas"])
        if rule_payload["documents"]:
            rule_doc = rule_payload["documents"][0]
            rule_meta = rule_payload["metadatas"][0]

    final_docs: list[str] = []
    final_metas: list[dict[str, Any]] = []
    if rule_doc:
        final_docs.append(rule_doc)
        final_metas.append(rule_meta)

    final_docs.extend(normal_docs[: n_results - 1])
    final_metas.extend(normal_metas[: n_results - 1])

    session_memory[user_id].append(
        {
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "sources": [meta.get("source", "") for meta in final_metas if meta.get("source") != "BOT_RULE"],
            "retrieved_ids": ranked_ids[:n_results],
            "fusion_method": selected_fusion_method,
        }
    )

    elapsed = time.time() - started_at
    stats["avg_time"] = (stats["avg_time"] * (stats["total_queries"] - 1) + elapsed) / stats["total_queries"]
    for metadata in final_metas:
        if metadata.get("source") not in ["BOT_RULE", None]:
            stats["popular_files"][metadata["source"]] += 1

    print(
        f"QUERY OK | {elapsed:.3f}s | fusion={selected_fusion_method} | "
        f"rrf_k={rrf_k} | alpha={alpha} | {len(final_docs)} results | User: {user_id[-8:]}"
    )
    return final_docs, final_metas, {
        "session_history": list(session_memory[user_id]),
        "stats": stats.copy(),
        "sources": list({meta.get("source") for meta in final_metas if meta.get("source") != "BOT_RULE"}),
        "fusion_method": selected_fusion_method,
        "rrf_k": rrf_k,
    }
