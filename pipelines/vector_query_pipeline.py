from __future__ import annotations

import re
import time
import unicodedata
from datetime import datetime
from typing import Any, Callable, Optional

from rank_bm25 import BM25Okapi


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
) -> tuple[dict[str, float], list[str]]:
    if bm25_index is None or not all_ids:
        return {}, []

    query_tokens = tokenize_text_fn(query)
    if not query_tokens:
        return {}, []

    bm25_raw = bm25_index.get_scores(query_tokens)
    raw_scores = {doc_id: float(bm25_raw[index]) for index, doc_id in enumerate(all_ids)}
    ranked_ids = [
        doc_id
        for doc_id, score in sorted(raw_scores.items(), key=lambda item: item[1], reverse=True)
        if score > 0
    ][:limit]
    return normalize_scores(raw_scores), ranked_ids


def run_hybrid_query(
    *,
    collection: Any,
    query: str,
    user_id: str,
    n_results: int,
    alpha: float,
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
    vector_results = collection.query(
        query_texts=[query],
        n_results=vector_candidate_limit,
        include=["documents", "metadatas", "distances"],
    )

    vector_ids = vector_results["ids"][0]
    vector_distances = vector_results["distances"][0]
    cosine_raw = {doc_id: 1.0 - distance for doc_id, distance in zip(vector_ids, vector_distances)}
    normalized_cosine = normalize_scores(cosine_raw)
    normalized_bm25, bm25_ids = top_bm25_candidates(
        query,
        bm25_index=bm25_index,
        all_ids=all_ids,
        limit=bm25_candidate_limit,
        tokenize_text_fn=tokenize_text_fn,
    )

    candidate_ids = list(dict.fromkeys([*vector_ids, *bm25_ids]))
    if bot_rule_id not in candidate_ids:
        candidate_ids.append(bot_rule_id)

    hybrid_scores: dict[str, float] = {}
    for doc_id in candidate_ids:
        cosine_score = normalized_cosine.get(doc_id, 0.0)
        bm25_score = normalized_bm25.get(doc_id, 0.0)
        hybrid_scores[doc_id] = alpha * cosine_score + (1 - alpha) * bm25_score
        if doc_id == bot_rule_id:
            hybrid_scores[doc_id] = 2.0

    ranked_ids = [doc_id for doc_id, _score in sorted(hybrid_scores.items(), key=lambda item: item[1], reverse=True)]
    top_ids = ranked_ids[: n_results + 5]
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

        metadata["hybrid_score"] = round(hybrid_scores.get(doc_id, 0.0), 6)
        metadata["vector_score"] = round(normalized_cosine.get(doc_id, 0.0), 6)
        metadata["bm25_score"] = round(normalized_bm25.get(doc_id, 0.0), 6)
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
        }
    )

    elapsed = time.time() - started_at
    stats["avg_time"] = (stats["avg_time"] * (stats["total_queries"] - 1) + elapsed) / stats["total_queries"]
    for metadata in final_metas:
        if metadata.get("source") not in ["BOT_RULE", None]:
            stats["popular_files"][metadata["source"]] += 1

    print(f"QUERY OK | {elapsed:.3f}s | alpha={alpha} | {len(final_docs)} results | User: {user_id[-8:]}")
    return final_docs, final_metas, {
        "session_history": list(session_memory[user_id]),
        "stats": stats.copy(),
        "sources": list({meta.get("source") for meta in final_metas if meta.get("source") != "BOT_RULE"}),
    }
