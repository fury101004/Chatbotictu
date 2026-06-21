# Defense Evidence

Tai lieu nay doi chieu code va ket qua kiem thu thuc te tai ngay `2026-06-14`.
Dataset benchmark goc `docs/evaluation/ictu_30_questions_dataset.json` khong bi sua.

## Evidence Matrix

| Chuc nang | File code va class/ham | Test lien quan | Lenh va ket qua | Han che con lai |
| --- | --- | --- | --- | --- |
| LangGraph controlled workflow | `services/llm/graph_service.py`: `RAGChatGraph._build`, `_SequentialGraph.invoke`; `services/chat/chat_service.py` | `tests/test_chat_api_endpoints.py`, `tests/test_rag_upload_flow.py` | Full pytest: `194 passed, 1 skipped` | Khi LangGraph khong import duoc, he thong dung sequential fallback co cung controlled nodes. |
| Bon RAG tool | `config/rag_tools.py`: `RAG_TOOL_PROFILES`, `get_tool_corpus_paths`, `get_tool_metadata_filter`; `orchestrators/rag_orchestrator.py::retrieve_context`; `services/rag/rag_service.py`: bon ham `retrieve_*_context` | `tests/test_rag_tool_sources.py`, `tests/test_vector_manager_payload.py` | Acceptance: 5 test source ownership pass | Corpus `academic_policies`, `student_faqs`, `general_ictu` hien chi co `.gitkeep`; chat se fallback khi chua nap du lieu. |
| RRF | `pipelines/vector_query_pipeline.py::reciprocal_rank_fusion`, `normalize_fusion_method`, `run_hybrid_query`; `config/settings.py::RRF_K` | `tests/test_vector_query_pipeline.py` | 6 RRF/fusion test pass; benchmark local ghi `fusion_method=rrf` | Chat luong phu thuoc chat luong hai ranking dau vao. |
| Hybrid Retrieval | `pipelines/vector_query_pipeline.py::run_hybrid_query`; `services/rag/langchain_retrievers.py::VectorStoreRetriever`; `repositories/vector_repository.py` | `tests/test_vector_query_pipeline.py`, `tests/test_langchain_retrievers.py` | Full pytest pass; benchmark dung local embedding, BM25 3395 chunks, RRF `k=60` | Vector backend can local model cache; neu cache thieu thi lexical fallback duoc dung. |
| Cross-Encoder | `services/reranker.py::CrossEncoderReranker`, `rerank_langchain_documents`; `services/rag/rag_results.py::_build_result_from_documents` | `tests/test_reranker.py` | 4 reranker test pass | Model duoc load `local_files_only`; neu khong co cache hoac predict loi thi giu ranking pre-rerank. |
| Citation | `services/rag/citation_serializer.py::serialize_citations`, `serialize_chat_payload`; `orchestrators/chat_orchestrator.py`; web/API controllers | `tests/test_citation_serializer.py`, `tests/test_web_security.py::WebCsrfSecurityTests::test_chat_citations_are_clean_for_user_and_detailed_for_admin` | Citation/security targeted suite pass | URL cong khai chi xuat hien neu metadata/source co HTTP(S) URL hop le. |
| Evaluation Dashboard | `controllers/web_controller.py::_evaluation_dashboard_required`; `routers/dashboard.py::_require_admin`; `controllers/api_controller.py::_require_admin_session`; `views/frontend/evaluation_dashboard.html` | `tests/test_web_security.py::WebCsrfSecurityTests::test_evaluation_dashboard_is_admin_only`, `test_legacy_dashboard_and_all_dashboard_data_routes_are_admin_only` | Anonymous 401/login redirect, user 403, admin 200/redirect; test pass | Dashboard phu thuoc eval log that; khong co du lieu se hien `Chưa có dữ liệu đánh giá.` va API loi se hien loi that. |
| Upload validation | `services/content/upload_validation.py::validate_text_upload`; `services/content/document_service.py::process_uploaded_documents` | `tests/test_upload_validation.py`, `tests/test_rag_upload_flow.py`, `tests/test_input_guard.py` | 45 upload/ingestion/input targeted test pass | Chi ho tro `.md`, `.markdown`, `.txt` UTF-8; PDF/DOCX bi tu choi vi pipeline chua doc duoc. |
| Ingestion jobs | `repositories/ingestion_repository.py::IngestionJobRepository`; `services/ingestion_queue.py::IngestionQueue` | `tests/test_ingestion_queue.py` | Queue completion/failure/not-found va resume tu checkpoint sau restart pass | Upload duoc checkpoint vao `DATA_DIR/ingestion_checkpoints`; neu checkpoint mat/hong thi job duoc danh dau `interrupted` thay vi xu ly lai khong an toan. |
| Benchmark | `tools/evaluation/evaluate_chatbot.py::evaluate_dataset`, `evaluate_case`, `build_markdown` | Dataset co dinh 30 cau; SHA-256 duoc ghi trong ket qua | Keyword mode: Route Accuracy `96.67%`; Top-1/Top-3 `86.67%`; MRR `0.88`; fallback `8`; latency min/max/mean/median/p95 `48.81/19934.01/6223.16/4412.59/12913.73 ms` | Full network-dependent flow da timeout sau hon 10 phut; ket qua cong bo dung keyword controlled mode. Sai: `local_005` route sang `general_ictu_rag`, expected source khong nam trong ranking. |
| Test | `pytest.ini`; `tests/conftest.py::GRADUATION_ACCEPTANCE_NODEIDS` | Toan bo `tests/` | Collect `195`; full `194 passed, 0 failed, 1 skipped`; acceptance `29 passed` | Live LLM E2E bi skip; local JWT test secret tao 4 canh bao do ngan hon khuyen nghi production. |

## Commands Run

```powershell
.\venv\Scripts\python.exe -m pytest --collect-only -q
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe -m pytest --collect-only -m graduation_acceptance -q
.\venv\Scripts\python.exe -m pytest -m graduation_acceptance -q
$env:HF_HUB_OFFLINE='1'; $env:TRANSFORMERS_OFFLINE='1'; .\venv\Scripts\python.exe tools/evaluation/evaluate_chatbot.py --router-mode keyword
.\venv\Scripts\python.exe -m compileall -q services repositories controllers routers orchestrators pipelines tools/evaluation/evaluate_chatbot.py
git diff --check
```

`ruff` va `black` khong co trong virtual environment va repository khong co cau hinh formatter/linter tuong ung.
`compileall` pass. `git diff --check` pass; Git chi canh bao chuyen LF sang CRLF tren Windows.

## Generated Evidence

- `docs/evaluation/current_benchmark_results.json`
- `docs/evaluation/current_benchmark_results.md`
- `docs/evaluation/current_test_results.json`
- `docs/evaluation/current_test_results.md`
- `docs/audit/defense_evidence.md`

## Files Changed

Core/config:

- `.env.example`
- `config/prompts/rag_router.md`
- `config/rag_tools.py`
- `config/settings.py`
- `models/chat.py`
- `pytest.ini`

Application/retrieval:

- `controllers/api_controller.py`
- `controllers/web_controller.py`
- `orchestrators/chat_orchestrator.py`
- `orchestrators/rag_orchestrator.py`
- `pipelines/chunking_pipeline.py`
- `pipelines/document_admin_pipeline.py`
- `pipelines/retrieval_pipeline.py`
- `pipelines/vector_query_pipeline.py`
- `repositories/ingestion_repository.py`
- `repositories/vector_repository.py`
- `routers/dashboard.py`
- `services/chat/chat_service.py`
- `services/content/document_service.py`
- `services/content/upload_validation.py`
- `services/eval_tracker.py`
- `services/ingestion_queue.py`
- `services/rag/citation_serializer.py`
- `services/rag/langchain_retrievers.py`
- `services/rag/rag_results.py`
- `services/rag/rag_service.py`
- `services/reranker.py`
- `services/vector/vector_store_service.py`
- `views/frontend/evaluation_dashboard.html`
- `views/frontend/templates/pages/chat.html`

Tests/evaluation:

- `tests/conftest.py`
- `tests/e2e_test_30_questions.py`
- `tests/test_chat_api_endpoints.py`
- `tests/test_citation_serializer.py`
- `tests/test_ingestion_pipeline.py`
- `tests/test_ingestion_queue.py`
- `tests/test_knowledge_base_service.py`
- `tests/test_langchain_retrievers.py`
- `tests/test_prompt_builder.py`
- `tests/test_rag_tool_sources.py`
- `tests/test_rag_upload_flow.py`
- `tests/test_rate_limit_monitor.py`
- `tests/test_reranker.py`
- `tests/test_upload_validation.py`
- `tests/test_vector_manager_payload.py`
- `tests/test_vector_query_pipeline.py`
- `tests/test_web_security.py`
- `tools/evaluation/evaluate_chatbot.py`

Documentation/report generators:

- `CHANGELOG.md`
- `README.md`
- `docs/ai_agent_design.md`
- `docs/demo_script.md`
- `docs/technical_summary.md`
- `tools/reporting/build_ai_agent_chatbot_report.py`
- `tools/reporting/build_assignment_report.py`
- `tools/reporting/build_week5_report.py`
- `tools/reporting/generate_ai_agent_diagrams.py`
- `tools/reporting/generate_assignment_chatbot_diagram.py`

Dedicated corpus placeholders:

- `data/primary_corpus/academic_policies/.gitkeep`
- `data/primary_corpus/general_ictu/.gitkeep`
- `data/primary_corpus/student_faqs/.gitkeep`

Khong commit, push GitHub hoac deploy Azure.
