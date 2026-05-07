from __future__ import annotations

from repositories.vector_repository import delete_vector_chunk


def delete_chunk_by_id(chunk_id: str) -> None:
    delete_vector_chunk(chunk_id)
