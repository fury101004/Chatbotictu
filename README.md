# ICTU AI Chatbot

Mô tả ngắn gọn:

- Đây là hệ thống chatbot hỗ trợ sinh viên Trường Đại học Công nghệ Thông tin và Truyền thông Thái Nguyên (ICTU).
- Dự án giải quyết bài toán hỏi đáp học vụ dựa trên Sổ tay sinh viên, tài liệu quy định, FAQ và Knowledge Base nội bộ.
- Đối tượng sử dụng chính là sinh viên cần tra cứu thông tin học vụ và quản trị viên cần nạp, quản lý, kiểm duyệt dữ liệu tri thức.

## 1. Tổng quan dự án

ICTU AI Chatbot là ứng dụng web và API hỏi đáp tiếng Việt được xây dựng bằng `FastAPI`, theo hướng AI Agent kết hợp Retrieval-Augmented Generation (RAG). Hệ thống ưu tiên trả lời dựa trên dữ liệu đã nạp trong `data/primary_corpus`, đặc biệt là bộ Sổ tay sinh viên các năm từ 2018-2019 đến 2025-2026 và các file câu hỏi tương ứng.

Luồng chatbot gồm các bước chính: chuẩn hóa câu hỏi, nhận diện intent đơn giản, định tuyến sang nhóm tri thức phù hợp, truy xuất ngữ cảnh bằng hybrid retrieval, sinh câu trả lời bằng LLM, gắn nguồn tham khảo và lưu lịch sử hội thoại. Dự án không tập trung vào tuyển sinh, điểm chuẩn hay gợi ý ngành; các câu hỏi ngoài phạm vi ICTU hoặc thiếu dữ liệu được xử lý bằng fallback an toàn hoặc yêu cầu người dùng bổ sung mốc áp dụng như năm học, khóa, học kỳ hoặc đợt.

Kiến trúc mã nguồn đi theo hướng Controller - Service - Repository - Pipeline - Orchestrator, có thể xem là một biến thể mở rộng của MVC: `views/` đảm nhiệm presentation, `controllers/` nhận request, `services/` xử lý nghiệp vụ, `repositories/` truy cập dữ liệu, `pipelines/` chứa các bước xử lý có thể tái sử dụng và `orchestrators/` điều phối luồng agent/RAG.

## 2. Tính năng chính

- Chat hỏi đáp bằng tiếng Việt qua giao diện web tại `/chat`.
- Truy xuất thông tin từ Sổ tay sinh viên và tài liệu học vụ trong `data/primary_corpus`.
- RAG theo nhóm tri thức: `student_handbook_rag`, `school_policy_rag`, `student_faq_rag` và fallback RAG.
- Hybrid retrieval kết hợp ChromaDB vector search và BM25 keyword search.
- Chunking tài liệu Markdown/TXT theo cấu trúc heading, kèm metadata như source, tool, document type, academic year.
- Quản lý tài liệu học vụ: upload file `.md`, `.markdown`, `.txt`, import seed corpus, reset/re-ingest vector store.
- Lưu lịch sử hội thoại theo `session_id` trong SQLite.
- Lưu memory hội thoại rút gọn theo tài khoản hoặc `session_id` trong SQLite, có TTL và giới hạn dung lượng.
- Giao diện quản trị gồm đăng nhập admin, upload tài liệu, quản lý vector, Knowledge Base, cấu hình và lịch sử chat.
- Duyệt Knowledge Base từ hội thoại: các cặp hỏi đáp có nguồn có thể được đưa vào trạng thái pending, admin có thể approve/reject.
- Citation/source grounding: response API và UI có danh sách nguồn; service chat cũng có bước append block nguồn tham khảo vào câu trả lời.
- Fallback khi thiếu dữ liệu: trả lời an toàn, hỏi lại khi câu hỏi thiếu năm học/khóa/học kỳ/đợt, hoặc thông báo không tìm thấy trong Knowledge Base.
- Web knowledge/web search cho câu hỏi thời sự ICTU nếu cấu hình `SEARXNG_URL`/`SEARXNG_API` và tùy chọn trích xuất nội dung web được bật.
- API token bằng partner key cho các endpoint `/api` và `/api/v1`.
- Rate limiting bằng `slowapi`, CSRF cho các thao tác admin web và middleware logging vào `logs/api.log`.
- Chuyển giao diện sáng/tối bằng theme toggle trên thanh điều hướng.

## 3. Kiến trúc hệ thống

| Layer | Thư mục/File liên quan | Vai trò |
|---|---|---|
| View / Presentation Layer | `views/frontend/templates/`, `views/frontend/assets/`, `views/web_view.py`, `views/api_view.py` | Render trang Jinja2, static assets, response builder cho web/API |
| Controller Layer | `controllers/web_controller.py`, `controllers/api_controller.py` | Định nghĩa route web, route API, validate form/body, kiểm tra auth/CSRF/token |
| Service Layer | `services/chat/`, `services/content/`, `services/vector/`, `services/llm/`, `services/config_service.py`, `services/admin_auth_service.py` | Xử lý nghiệp vụ chat, upload/import tài liệu, Knowledge Base, auth admin, runtime config, gọi LLM |
| Repository Layer | `repositories/`, `config/db.py` | Truy cập SQLite, vector repository, upload records, chat history, Knowledge Base, web knowledge |
| Pipeline Layer | `pipelines/` | Chunking, indexing, embedding, retrieval flow, vector query, document admin, Knowledge Base grouping/search |
| Orchestrator Layer | `orchestrators/chat_orchestrator.py`, `orchestrators/rag_orchestrator.py`, `services/llm/graph_service.py` | Điều phối state của chatbot, route tool RAG, gọi retrieval, generate answer, finalize/save history |
| Retrieval / RAG Layer | `services/rag/`, `services/vector/vector_store_service.py`, `pipelines/retrieval_pipeline.py`, `pipelines/vector_query_pipeline.py` | Router RAG, hybrid retrieval, lexical fallback, scope guard, citation/source merge, web search merge |
| LLM Layer | `services/llm/`, `providers/` | Quản lý provider/model, gọi Groq/Ollama, fallback khi lỗi/rate limit, prompt chain bằng LangChain |
| Data Layer | `data/`, `vectorstore/`, `logs/`, `.env` | Corpus Markdown, SQLite database, ChromaDB persistent store, system prompt, bot rules, log runtime |

Luồng chat thực tế:

```text
User/Web/API
  -> controllers
  -> services.chat.chat_service
  -> RAGChatGraph / orchestrators
  -> services.rag + vector/lexical/web retrieval
  -> services.llm / providers
  -> repositories lưu history + review state
  -> response có answer, sources, metadata
```

## 4. Cấu trúc thư mục

```text
project/
├── config/
│   ├── app_factory.py
│   ├── asgi.py
│   ├── db.py
│   ├── middleware.py
│   ├── rag_tools.py
│   └── settings.py
├── controllers/
│   ├── api_controller.py
│   └── web_controller.py
├── services/
│   ├── chat/
│   ├── content/
│   ├── llm/
│   ├── rag/
│   ├── search_backends/
│   └── vector/
├── repositories/
├── pipelines/
├── orchestrators/
├── providers/
├── models/
├── views/
│   ├── frontend/assets/
│   └── frontend/templates/
├── data/
│   ├── bot-rule.md
│   ├── systemprompt.md
│   ├── intents/
│   └── primary_corpus/
│       └── student_handbooks/
├── tests/
├── tools/
├── scripts/
├── docs/
├── main.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-search.txt
├── .env.example
└── README.md
```

## 5. Công nghệ sử dụng

- Python `3.11` theo `.python-version` và Docker base image `python:3.11-slim-bookworm`.
- FastAPI, Uvicorn, Starlette, Jinja2.
- SQLite cho runtime config, chat history, chat memory, upload records, review state và web knowledge.
- ChromaDB persistent store tại `vectorstore/`.
- `sentence-transformers` với model embedding `paraphrase-multilingual-MiniLM-L12-v2`.
- `rank-bm25` cho keyword retrieval.
- LangGraph nếu cài được; nếu không có thì `RAGChatGraph` tự chạy bằng sequential fallback.
- LangChain Core cho prompt chain.
- Groq và Ollama là provider LLM mặc định trong `LLM_PROVIDER_ORDER`; code cũng có provider Gemini/OpenAI cho hướng mở rộng.
- `slowapi` cho rate limiting, `PyJWT` cho partner API token.
- `httpx` cho LLM provider và web search service.

## 6. Cấu hình môi trường

Tạo file `.env` từ `.env.example`:

```powershell
Copy-Item .env.example .env
```

Các nhóm biến quan trọng:

| Nhóm | Biến |
|---|---|
| App/security | `APP_NAME`, `ENVIRONMENT`, `PARTNER_API_KEY`, `JWT_SECRET`, `SESSION_SECRET` |
| Web auth | `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_ROLE`, `USER_USERNAME`, `USER_PASSWORD`, `USER_ROLE` |
| Runtime chunking | `CHUNK_SIZE`, `CHUNK_OVERLAP` |
| Rate limit | `API_RATE_CHAT`, `API_RATE_UPLOAD`, `API_RATE_ADMIN` |
| Path | `DATA_DIR`, `LOG_DIR`, `DB_PATH`, `QA_CORPUS_ROOT`, `RAG_UPLOAD_ROOT`, `VECTORSTORE_DIR`, `SYSTEM_PROMPT_PATH`, `BOT_RULE_PATH` |
| LLM | `GROQ_API_KEY`, `GROQ_API_BASE_URL`, `OLLAMA_BASE_URL`, `LLM_PROVIDER_ORDER`, `LLM_MODEL_ROTATION`, `GROQ_MODEL_ORDER`, `OLLAMA_MODEL_ORDER` |
| Web search tùy chọn | `SEARXNG_URL`/`SEARXNG_API`, `TRAFILATURA_URL`/`TRAFILATURA_API`, `WEB_KB_*` |

Tài khoản admin mặc định trong môi trường development theo `.env.example`:

```text
ADMIN_USERNAME=admin@gmail.com
ADMIN_PASSWORD=123456
ADMIN_ROLE=admin
USER_USERNAME=student
USER_PASSWORD=123456
USER_ROLE=user
```

Khi `ENVIRONMENT=production`, code sẽ từ chối chạy nếu vẫn dùng secret mặc định hoặc mật khẩu admin/user mặc định. Cần đổi `PARTNER_API_KEY`, `JWT_SECRET`, `SESSION_SECRET`, `ADMIN_PASSWORD` và `USER_PASSWORD` trước khi deploy.

## 7. Cài đặt và chạy dự án

Tạo môi trường ảo:

```powershell
py -3.11 -m venv venv
.\venv\Scripts\activate
```

Cài dependencies:

```powershell
pip install -r requirements.txt
```

Nếu dùng phần web search local/ngoài service có sẵn:

```powershell
pip install -r requirements-search.txt
```

Chạy ứng dụng:

```powershell
python -m uvicorn config.asgi:app --reload
```

Entrypoint thật của app là `config.asgi:app`. File `main.py` chỉ export `app` và `templates` để giữ tương thích import.

Các URL chính:

- Web home: `http://127.0.0.1:8000/`
- Chat: `http://127.0.0.1:8000/chat`
- Login: `http://127.0.0.1:8000/login`
- Admin login alias: `http://127.0.0.1:8000/admin/login`
- Data loader: `http://127.0.0.1:8000/data-loader`
- Vector manager: `http://127.0.0.1:8000/vector-manager`
- Knowledge Base: `http://127.0.0.1:8000/knowledge-base`
- Config: `http://127.0.0.1:8000/config`
- History: `http://127.0.0.1:8000/history`
- API docs mặc định FastAPI: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

## 8. Quy trình dữ liệu và Knowledge Base

Dữ liệu gốc hiện có:

- `data/primary_corpus/student_handbooks/`: Sổ tay sinh viên các năm `2018-2019` đến `2025-2026`.
- Mỗi năm có file `.md` nội dung dài và file `.questions.md` chứa bộ Q&A được dùng để tăng chất lượng retrieval.
- `data/systemprompt.md`: system prompt.
- `data/bot-rule.md`: quy tắc/giọng điệu bot được inject vào vector store.
- `data/intents/`: dữ liệu intent đơn giản như greetings/chitchat.

Nạp dữ liệu:

- Qua UI admin: vào `/data-loader`, upload file hoặc import seed corpus.
- Qua endpoint web admin: `POST /import-qa-corpus`.
- Qua API token: `POST /api/v1/upload`.

Các file upload được lưu theo tool RAG trong `data/rag_uploads/<tool_name>/`. Khi embedding backend sẵn sàng, file được chunk và index vào ChromaDB. Nếu embedding backend chưa sẵn sàng, file vẫn được lưu và trả warning để có thể re-ingest sau.

Knowledge Base page `/knowledge-base` tổng hợp:

- vector entries từ ChromaDB;
- cặp hỏi đáp từ lịch sử chat;
- danh sách Q&A đã approve;
- trạng thái review `pending`, `approved`, `rejected`.

Khi câu trả lời có nguồn rõ ràng, hệ thống có thể đưa Q&A vào hàng chờ review. Admin có thể approve để ghi Q&A thành Markdown trong `_knowledge_base_chat` và index lại vào vector store.

## 9. API chính

Lấy token:

```http
POST /api/auth/token
POST /api/v1/auth/token
Content-Type: application/x-www-form-urlencoded

partner_key=<PARTNER_API_KEY>
```

Chat API:

```http
POST /api/chat
POST /api/v1/chat
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "message": "Sổ tay sinh viên 2025-2026 áp dụng cho đối tượng nào?",
  "session_id": "demo-session",
  "llm_model": "auto"
}
```

Các endpoint khác:

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/health`, `/api/health`, `/api/v1/health` | Kiểm tra app, LLM configured và embedding backend |
| `POST` | `/api/v1/upload` | Upload tài liệu Markdown/TXT bằng bearer token |
| `GET` | `/api/v1/knowledge-base` | Lấy payload Knowledge Base bằng bearer token |
| `GET` | `/api/v1/metrics/rate-limit-429` | Xem thống kê rate limit/LLM 429 |
| `POST` | `/api/v1/metrics/rate-limit-429/reset` | Reset thống kê 429 |

## 10. Giao diện quản trị

Các trang admin web dùng session cookie, CSRF token và `services/admin_auth_service.py`.

| Trang | Vai trò |
|---|---|
| `/login` | Đăng nhập admin hoặc user/student |
| `/admin/login` | Alias đăng nhập admin |
| `/data-loader` | Upload tài liệu, chọn RAG tool, import seed corpus |
| `/vector-manager` | Xem thống kê vector chunks, xóa source/chunk, reset vector store |
| `/knowledge-base` | Tìm kiếm vector/chat knowledge, approve/reject Q&A |
| `/config` | Chỉnh chunk size, overlap, system prompt/bot rules và re-ingest |
| `/history` | Xem lịch sử hội thoại |

Các trang admin sẽ redirect về `/login` nếu chưa đăng nhập. Tài khoản role `user`/`student` chỉ được vào `/chat`; nếu nhập trực tiếp URL quản trị sẽ được chuyển về `/chat`.

## 11. Kiểm thử

Chạy toàn bộ test:

```powershell
.\venv\Scripts\python.exe -m pytest
```

Một số nhóm test đang có trong `tests/`:

- Web security, CSRF, admin login: `test_web_security.py`.
- API chat/health/token: `test_chat_api_endpoints.py`.
- Runtime config và DB migration: `test_runtime_config.py`.
- Upload/RAG routing/retrieval planner: `test_rag_upload_flow.py`.
- Knowledge Base approve/search/grouping: `test_knowledge_base_service.py`.
- Golden regression cho Sổ tay sinh viên theo năm: `test_golden_handbook_regression.py`.
- Prompt builder, multilingual, LLM rotation, LangChain retrievers, web search và rate limit monitor.

Lệnh smoke test nhanh thường dùng khi sửa auth/web:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_web_security.py tests\test_runtime_config.py
```

## 12. Docker

Build và chạy bằng Docker Compose:

```powershell
docker-compose up --build
```

Nếu máy có Docker Compose plugin thì có thể dùng lệnh tương đương:

```powershell
docker compose up --build
```

Image mặc định được tag là `ictu-rag-api:local`. Có thể đổi tag trước khi build/push:

```powershell
$env:DOCKER_IMAGE="your-dockerhub-user/ictu-rag-api:latest"
docker-compose build
docker push $env:DOCKER_IMAGE
```

Nếu máy local không đủ RAM/dung lượng để build, dùng workflow GitHub Actions `Build Docker image`.
Workflow này push image lên GitHub Container Registry:

```powershell
docker pull ghcr.io/<github-owner>/<repo-name>:latest
$env:DOCKER_IMAGE="ghcr.io/<github-owner>/<repo-name>:latest"
docker-compose up -d --no-build
```

`docker-compose.yml` mount các thư mục runtime:

- `./data:/app/data`
- `./vectorstore:/app/vectorstore`
- `./logs:/app/logs`
- `./views/frontend/templates:/app/views/frontend/templates`
- `./views/frontend/assets:/app/views/frontend/assets`

Container expose port `8000` và healthcheck vào `/api/v1/health`.

## 13. Lưu ý triển khai và vận hành

- Không commit `.env`, database SQLite, vector store, logs hoặc dữ liệu upload runtime.
- Production bắt buộc thay toàn bộ secret mặc định và mật khẩu admin mặc định.
- Embedding backend có thể cần cache Hugging Face local hoặc kết nối mạng để tải model `paraphrase-multilingual-MiniLM-L12-v2`.
- Nếu không có `GROQ_API_KEY` và Ollama local không chạy, app vẫn boot được nhưng LLM generation sẽ lỗi khi cần sinh câu trả lời từ context.
- Web search không tự hoạt động nếu chưa cấu hình `SEARXNG_URL`/`SEARXNG_API`; khi chưa cấu hình, retrieval dùng dữ liệu local và fallback.
- Corpus chính nên được import/re-ingest sau khi thay `CHUNK_SIZE`, `CHUNK_OVERLAP`, system prompt hoặc cập nhật tài liệu nguồn.
- Phạm vi trả lời nên giữ ở thông tin ICTU và tài liệu học vụ đã có; không nên quảng bá chatbot như hệ tư vấn tuyển sinh/điểm chuẩn.

## 14. Tài liệu liên quan

- `CHANGELOG.md`
- `docs/technical_summary.md`
- `docs/demo_script.md`
- `docs/ai_agent_design.md`
- `docs/rag_regression_and_ops.md`
- `docs/langchain_langgraph_review.md`
- `views/frontend/README.md`
- `tools/README.md`
