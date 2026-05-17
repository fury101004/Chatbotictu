from __future__ import annotations

from typing import Any

from services.vector.vector_store_service import get_collection, get_collection_readonly, query_documents


def get_vector_collection():
    return get_collection()


def get_vector_collection_readonly():
    return get_collection_readonly()


def count_vector_chunks() -> int:
    return get_vector_collection().count()


def count_vector_chunks_readonly() -> int:
    return get_vector_collection_readonly().count()


def list_vector_chunks(*, include_documents: bool = True) -> dict[str, list[Any]]:
    include_fields = ["metadatas"]
    if include_documents:
        include_fields.append("documents")
    return get_vector_collection().get(include=include_fields)


def list_vector_sources() -> set[str]:
    data = get_vector_collection().get(include=["metadatas"])
    return {
        str(metadata.get("source", "") or "")
        for metadata in data.get("metadatas", [])
        if metadata
    }


def fetch_documents_by_source(source: str) -> tuple[list[str], list[dict[str, Any]]]:
    data = get_vector_collection().get(
        where={"source": str(source or "")},
        include=["documents", "metadatas"],
    )
    documents = [str(document or "") for document in data.get("documents", [])]
    metadatas = [dict(metadata or {}) for metadata in data.get("metadatas", [])]
    return documents, metadatas


def search_vector_documents(
    query: str,
    *,
    user_id: str = "default",
    n_results: int = 8,
    alpha: float = 0.75,
):
    return query_documents(
        query,
        user_id=user_id,
        n_results=n_results,
        alpha=alpha,
    )


def delete_vector_chunk(chunk_id: str) -> None:
    normalized_chunk_id = str(chunk_id or "").strip()
    if not normalized_chunk_id:
        raise ValueError("chunk_id is required")
    get_vector_collection().delete(ids=[normalized_chunk_id])


def delete_vector_source(source: str) -> None:
    normalized_source = str(source or "").strip()
    if not normalized_source:
        raise ValueError("source is required")
    get_vector_collection().delete(where={"source": normalized_source})

