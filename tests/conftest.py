from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

GRADUATION_ACCEPTANCE_NODEIDS = frozenset(
    {
        "tests/test_vector_query_pipeline.py::ReciprocalRankFusionTests::test_rrf_combines_independent_rankings_by_stable_id",
        "tests/test_vector_query_pipeline.py::ReciprocalRankFusionTests::test_rrf_k_is_configurable",
        "tests/test_vector_query_pipeline.py::ReciprocalRankFusionTests::test_rrf_rejects_invalid_k",
        "tests/test_vector_query_pipeline.py::FusionMethodTests::test_rrf_is_default_for_unknown_or_empty_method",
        "tests/test_vector_query_pipeline.py::FusionMethodTests::test_weighted_fusion_remains_available",
        "tests/test_vector_query_pipeline.py::HybridQueryRrfIntegrationTests::test_hybrid_query_applies_tool_filter_and_persists_rrf_rank_metadata",
        "tests/test_rag_tool_sources.py::RagToolSourceOwnershipTests::test_each_tool_exposes_a_distinct_retrieval_function",
        "tests/test_rag_tool_sources.py::RagToolSourceOwnershipTests::test_each_tool_uses_one_existing_dedicated_seed_directory",
        "tests/test_rag_tool_sources.py::RagToolSourceOwnershipTests::test_file_at_shared_corpus_root_has_no_owner",
        "tests/test_rag_tool_sources.py::RagToolSourceOwnershipTests::test_paths_inside_each_seed_directory_map_to_its_owner",
        "tests/test_rag_tool_sources.py::RagToolSourceOwnershipTests::test_standardized_tool_order_contains_four_controlled_tools",
        "tests/test_citation_serializer.py::CitationSerializerTests::test_admin_citation_keeps_debug_detail_but_removes_secrets_and_absolute_path",
        "tests/test_citation_serializer.py::CitationSerializerTests::test_chat_payload_projects_user_and_admin_citations",
        "tests/test_citation_serializer.py::CitationSerializerTests::test_user_citation_is_clean_and_short",
        "tests/test_upload_validation.py::UploadValidationTests::test_accepts_supported_utf8_markdown",
        "tests/test_upload_validation.py::UploadValidationTests::test_rejects_binary_signature_even_with_text_extension",
        "tests/test_upload_validation.py::UploadValidationTests::test_rejects_dangerous_filename",
        "tests/test_upload_validation.py::UploadValidationTests::test_rejects_decode_error",
        "tests/test_upload_validation.py::UploadValidationTests::test_rejects_empty_file",
        "tests/test_upload_validation.py::UploadValidationTests::test_rejects_extension_mime_mismatch",
        "tests/test_upload_validation.py::UploadValidationTests::test_rejects_file_over_size_limit",
        "tests/test_upload_validation.py::UploadValidationTests::test_rejects_unsupported_extension",
        "tests/test_ingestion_queue.py::IngestionQueueTests::test_failed_job_records_error",
        "tests/test_ingestion_queue.py::IngestionQueueTests::test_job_creation_and_completion_status",
        "tests/test_ingestion_queue.py::IngestionQueueTests::test_status_polling_returns_not_found_for_unknown_job",
        "tests/test_ingestion_queue.py::IngestionQueueTests::test_unfinished_job_resumes_after_restart_from_durable_checkpoint",
        "tests/test_web_security.py::WebCsrfSecurityTests::test_evaluation_dashboard_is_admin_only",
        "tests/test_web_security.py::WebCsrfSecurityTests::test_legacy_dashboard_and_all_dashboard_data_routes_are_admin_only",
        "tests/test_web_security.py::WebCsrfSecurityTests::test_chat_citations_are_clean_for_user_and_detailed_for_admin",
    }
)


def pytest_collection_modifyitems(items):
    for item in items:
        if item.nodeid in GRADUATION_ACCEPTANCE_NODEIDS:
            item.add_marker(pytest.mark.graduation_acceptance)


@pytest.fixture(autouse=True)
def isolate_runtime_state_between_tests(tmp_path, monkeypatch):
    from config.limiter import limiter
    from services.memory_store import MemoryStore

    test_memory_store = MemoryStore(db_path=tmp_path / "chat_memory.db")
    monkeypatch.setattr(
        "services.chat.chat_service.get_default_memory_store",
        lambda: test_memory_store,
    )

    storage = getattr(limiter, "_storage", None)
    if storage is not None and hasattr(storage, "reset"):
        storage.reset()
    yield
