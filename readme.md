# ICTU AI Chatbot

 Mục tiêu là mô tả đúng trạng thái thực tế của dự án, tập trung vào kiến trúc, luồng xử lý, cách chạy và các điểm còn cần hoàn thiện.

## Tổng Quan

Đây là ứng dụng FastAPI cho chatbot hỗ trợ người học trong phạm vi ICTU. Hệ thống hiện đã vượt ra ngoài một chatbot FAQ đơn giản và gồm các khối chính sau:

- Chat web và REST API.
- RAG theo 3 nhóm tri thức: `student_handbook_rag`, `school_policy_rag`, `student_faq_rag`.
- Vector store dùng ChromaDB kết hợp BM25/hybrid retrieval.
- Upload tài liệu Markdown/TXT theo từng nhóm RAG.
- Knowledge Base hợp nhất từ:
  - tài liệu đã index trong vector store;
  - cặp hỏi đáp chatbot đã duyệt thủ công;
  - web knowledge cache đáng tin cậy từ kết quả tìm kiếm ICTU.
- Web search ưu tiên domain chính thức của ICTU, có cơ chế cache và TTL.
- Trang quản trị: `chat`, `data-loader`, `vector-manager`, `knowledge-base`, `config`, `history`, `cskh-panel`.

## Kiến Trúc Thực Tế

### Entry Points

- `main.py`: re-export `config.asgi:app`.
- `config/asgi.py`: tạo `app = create_app()`.
- `config/app_factory.py`: khởi tạo FastAPI, middleware, static files, web routes, API routes và CSKH websocket routes.

### Các Lớp Chính

- `controllers/`
  - `web_controller.py`: route giao diện web.
  - `api_controller.py`: route API `/api/v1/...`.
- `services/`
  - `chat_service.py`: điều phối luồng chat.
  - `graph_service.py`: wrapper cho LangGraph, có fallback sequential.
  - `rag_service.py`: router RAG, lexical fallback, vector retrieval, web search merge.
  - `vector_store_service.py`: ChromaDB + BM25 + smart chunking.
  - `multilingual_service.py`: prompt builder, chọn ngôn ngữ, gọi LLM.
  - `knowledge_base_service.py`: hợp nhất vector data và chat Q&A, duyệt Q&A vào KB.
  - `document_service.py`: upload/import/xóa/reset tài liệu và payload cho Vector Manager.
  - `web_search.py`: tìm web ICTU, ưu tiên site chính thức.
  - `web_knowledge_service.py`: cache câu trả lời web đáng tin cậy.
  - `llm_service.py`: rotation Groq/Ollama.
  - `gemini_service.py`: service cũ/thử nghiệm, hiện không phải luồng chat chính.
- `config/`
  - `settings.py`: một phần cấu hình qua `.env`.
  - `db.py`: SQLite, config, prompt, chat history, approved chat, web knowledge.
  - `middleware.py`: logging, rate limit, session, CORS.
- `views/`
  - Jinja templates và API/web response builders.
- `tests/`
  - Unit tests cho LLM rotation, RAG upload, knowledge base, web search, web knowledge, prompt builder và scope detection.

## Luồng Xử Lý Chat

1. Request đi vào `/chat` hoặc `/api/v1/chat`.
2. `services/chat_service.py` chuẩn hóa input, lưu tin nhắn user vào SQLite.
3. `services/rag_service.py` chọn nhóm tri thức bằng LLM router hoặc keyword router.
4. Hệ thống truy xuất theo thứ tự ưu tiên:
   - trusted web knowledge cache;
   - corpus local theo tool;
   - vector search / hybrid search;
   - lexical fallback;
   - web search ICTU khi cần dữ liệu mới.
5. `services/multilingual_service.py` tạo final prompt và gọi `services/llm_service.py`.
6. Bot lưu câu trả lời, cập nhật `SESSION_MEMORY`; nếu câu trả lời đến từ web search thì có thể đưa vào `web_search_knowledge`.

## Tính Năng Nổi Bật

- RAG chia nhóm dữ liệu thay vì nhét tất cả vào một kho duy nhất.
- Có cơ chế fallback khi:
  - không có embedding backend;
  - không có LLM network;
  - vector retrieval lỗi;
  - web search không khả dụng.
- Knowledge Base có chức năng duyệt thủ công câu trả lời từ lịch sử chat để đưa ngược vào retrieval.
- Model chat có UI chọn model và hỗ trợ rotation `round-robin`/`fixed`.
- Web search có chiến lược official-first cho ICTU.
- Có websocket CSKH cho trường hợp cần chuyển sang người thật.

## Thư Mục Và Dữ Liệu Quan Trọng

- `data/bot_config.db`: SQLite runtime.
- `data/systemprompt.md`: system prompt hiện hành.
- `data/bot-rule.md`: bot rule chèn vào retrieval.
- `data/qa_generated_fixed/`: seed corpus.
- `data/rag_uploads/`: tài liệu upload theo tool.
- `vectorstore/`: Chroma persistent store.
- `logs/api.log`: access/application log.
- `reports/`, `docs/`, `scripts/`: báo cáo, tài liệu nội bộ, script phân tích/evaluate.

## Biến Môi Trường Cần Lưu Ý

### Bắt Buộc Cho Production

- `PARTNER_API_KEY`
- `JWT_SECRET`
- `SESSION_SECRET`

### LLM

- `GROQ_API_KEY`
- `LLM_PROVIDER_ORDER`
- `GROQ_MODEL_ORDER`
- `OLLAMA_MODEL` hoặc `OLLAMA_MODEL_ORDER`
- `OLLAMA_BASE_URL`
- `LLM_MODEL_ROTATION`

### Web Search / Web Knowledge

- `SEARXNG_URL` hoặc `SEARXNG_API`
- `TRAFILATURA_URL` hoặc `TRAFILATURA_API`
- `WEB_KB_TRUSTED_THRESHOLD`
- `WEB_KB_MIN_SCORE`
- `WEB_KB_TTL_DAYS`
- `WEB_KB_REALTIME_TTL_DAYS`

### Legacy / Chưa Phải Luồng Chat Chính

- `GEMINI_API_KEY`

## Cách Chạy Local

Ví dụ trên Windows PowerShell:

```powershell
py -3.11 -m venv venv
.\venv\Scripts\pip.exe install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn config.asgi:app --reload
```

Nếu cần bộ web search phụ trợ:

```powershell
.\venv\Scripts\pip.exe install -r requirements-search.txt
```

Sau khi chạy:

- Web UI: `http://127.0.0.1:8000/`
- API health: `http://127.0.0.1:8000/api/v1/health`

## API Và Màn Hình Chính

### API

- `POST /api/v1/auth/token`
- `POST /api/v1/chat`
- `POST /api/v1/upload`
- `GET /api/v1/knowledge-base`
- `GET /api/v1/health`

### Web Pages

- `/`
- `/chat`
- `/data-loader`
- `/vector-manager`
- `/knowledge-base`
- `/config`
- `/history`
- `/cskh-panel`

## Kết Quả Verify Khi Review

Đã đọc các nhóm file: `config/`, `controllers/`, `services/`, `views/`, `tests/`, `Dockerfile`, `docker-compose.yml`, `Caddyfile`, `docs/`.

Đã chạy unit test bằng lệnh:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

Đã chạy benchmark router/retrieval bằng lệnh:

```powershell
.\venv\Scripts\python.exe scripts\evaluate_chatbot.py
```

Kết quả sau đợt review và cleanup ngày `16/04/2026`:

- `29 tests`
- `OK`
- benchmark: `31` câu hỏi, `25` câu có nhãn nguồn
- route accuracy: `100%`
- source hit rate: `100%`
- source top-1 hit rate: `96%`
- source MRR: `0.9733`
- avg latency: `1061.65 ms`
- không còn failing case benchmark

Phạm vi test hiện có:

- LLM rotation và model selection.
- DB schema migration.
- Session middleware config.
- Prompt builder.
- Upload/index fallback.
- Knowledge base merge và approve chat.
- Vector manager payload.
- ICTU scope detection.
- Web search.
- Web knowledge cache.

Chưa thấy integration/smoke test rõ ràng cho:

- Docker deployment path mapping trong container thật.
- Web UI end-to-end.
- Startup smoke test sau migration trên DB thực tế có dữ liệu lớn.

## Đã Xử Lý Trong Đợt Này

- Thêm migration tự động cho `chat_history.session_id` và index theo session.
- Đổi `SessionMiddleware` sang secret ổn định qua `settings`, hỗ trợ `SESSION_SECRET`.
- Dọn `Dockerfile`, bỏ phần cài `torch` trùng lặp.
- Đồng bộ `docker-compose.yml` với đường dẫn template/static thật của app.
- Cắt một liên kết legacy không cần thiết: `scripts/evaluate_chatbot.py` không còn phụ thuộc vào `gemini_service`.
- Làm `gemini_service` lazy-import hơn để giảm noise khi luồng chính không dùng Gemini.
- Mở rộng bộ benchmark lên `31` câu hỏi, trong đó `25` câu có nhãn nguồn để đo router/retrieval.
- Viết lại `scripts/evaluate_chatbot.py` theo nội dung sạch hơn và sinh `reports/generated/eval_results.*` mới.
- Đồng bộ lại tài liệu tổng hợp để không còn số liệu cũ `13` câu benchmark.

## Đánh Giá Tiến Độ Theo Đề Cương

Theo lịch trong PDF, kế hoạch 10 tuần chạy từ `09/03/2026` đến `22/05/2026`. Tính theo mốc thời gian thực, ngày review `16/04/2026` đang nằm trong tuần 6 của kế hoạch.

Nếu tính theo mức độ hoàn thành deliverable, dự án đã vượt mức tuần 6:

- Tuần 1-5: đã có phần phân tích, thu thập tri thức, kho dữ liệu và retrieval.
- Tuần 6-8: đã có router, graph orchestration, prompt builder, tích hợp model và 3 nhóm tri thức.
- Tuần 9: đã có Web chat, API, trang quản trị dữ liệu và benchmark có thể demo.
- Tuần 10: đã có bộ test >= 30 câu hỏi, tài liệu tổng hợp, kết quả benchmark và minh chứng unit test.

Kết luận thẳng:

- Nếu chấm theo deliverable để demo/báo cáo: dự án đang ở mức `week 9 hoàn thành` và `week 10 đang hoàn thiện`.
- Nếu đối chiếu rất sát đề cương PDF: chưa khớp 100% vì vector store vẫn là `ChromaDB` thay vì `FAISS`, và nhóm tool nghiệp vụ chưa tách đúng tên như đề cương.

## Vấn Đề Còn Tồn Đọng

### 1. Mức Độ Trung Bình: Repo Đang Có Lỗi Encoding Ở Nhiều Nơi

README cũ, một số template, script, `config/rag_tools.py` và một số nội dung hiển thị bị lỗi dấu tiếng Việt.

Tác động:

- Giao diện và tài liệu không nhất quán.
- Keyword routing/cố định danh corpus có thể khó debug hơn.
- Khó bàn giao và khó bảo trì.

### 2. Mức Độ Trung Bình: Cấu Hình Security Vẫn Mang Tính Dev

Code đang cho phép default:

- `PARTNER_API_KEY = "dev-partner-key"`
- `JWT_SECRET = "dev-jwt-secret"`
- `SESSION_SECRET` sẽ fallback về `JWT_SECRET` nếu chưa khai báo.
- CORS `allow_origins=["*"]` kèm `allow_credentials=True`.

Nếu đem lên môi trường thật mà chưa harden, ranh giới xác thực và truy cập API sẽ yếu.

### 3. Mức Độ Trung Bình: Còn Dấu Vết Service Cũ

`services/gemini_service.py` và dependency `google.generativeai` vẫn tồn tại, nhưng luồng chat chính hiện đi qua `services/llm_service.py`.

Tác động:

- Dễ gây nhầm service nào đang là service chính.
- Tăng chi phí bảo trì dependency.

## Ưu Tiên Xử Lý Tiếp Theo

1. Chuẩn hóa encoding UTF-8 cho README, templates, script và metadata corpus.
2. Siết CORS theo domain thật và bắt buộc set secret production riêng cho JWT/session.
3. Tách rõ code active vs legacy, đặc biệt quanh Gemini và các script cũ.
4. Bổ sung smoke test cho app startup và UI chính.

## Đánh Giá Tổng Kết

Dự án có hướng đi tốt, đã có nhiều năng lực thực dụng hơn một chatbot demo thông thường: RAG chia nhóm, hybrid retrieval, web search cache, knowledge base duyệt thủ công và test unit cho các feature mới. Sau đợt cleanup này, các điểm nghẽn vận hành rõ nhất quanh session schema, session secret và deploy config đã được xử lý; phần còn lại chủ yếu là hardening, encoding và tách legacy cho gọn repo.
