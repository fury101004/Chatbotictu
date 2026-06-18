from __future__ import annotations

from services.content.document_service import clear_vector_manager_cache
from services.content.knowledge_base_service import clear_knowledge_base_cache
from repositories.vector_repository import delete_vector_chunk


def delete_chunk_by_id(chunk_id: str) -> None:
    delete_vector_chunk(chunk_id)
    clear_vector_manager_cache()
    clear_knowledge_base_cache()
