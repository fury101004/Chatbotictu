## RAG Regression and Ops Checklist

### 1) UTF-8 normalization for corpus/prompt/template
```powershell
$env:PYTHONIOENCODING='utf-8'
.\venv\Scripts\python.exe tools\data_pipeline\normalize_utf8_corpus.py --include-clean-data --report reports/utf8_normalization_report_apply.json
```

Post-check (expect `Changed 0 files`):
```powershell
.\venv\Scripts\python.exe tools\data_pipeline\normalize_utf8_corpus.py --dry-run --include-clean-data --report reports/utf8_normalization_report_postcheck.json
```

### 2) Re-ingest after metadata schema changes
```powershell
$env:PYTHONIOENCODING='utf-8'
.\venv\Scripts\python.exe -c "from services.content.document_service import reingest_uploaded_documents; print(reingest_uploaded_documents())"
```

### 3) Run regression tests (year-isolation + metadata + security)
```powershell
.\venv\Scripts\python.exe -m unittest ^
  tests.test_golden_handbook_regression ^
  tests.test_chunk_metadata ^
  tests.test_vector_manager_payload ^
  tests.test_runtime_config ^
  tests.test_rate_limit_monitor
```

### 4) Live LLM E2E (opt-in)
```powershell
$env:RUN_LIVE_LLM_E2E='1'
.\venv\Scripts\python.exe -m unittest tests.test_e2e_live_llm
```

### 5) Load test + 429 monitoring
```powershell
.\venv\Scripts\python.exe tools\evaluation\load_test_chat_api.py `
  --base-url http://127.0.0.1:5000 `
  --partner-key "<PARTNER_API_KEY>" `
  --total-requests 120 `
  --concurrency 12 `
  --reset-metrics-before-run `
  --output reports/load_test_chat_api_report.json
```

429 metrics endpoint:
- `GET /api/v1/metrics/rate-limit-429`
- `POST /api/v1/metrics/rate-limit-429/reset`

