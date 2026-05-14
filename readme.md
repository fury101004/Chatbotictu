# ICTU AI Chatbot

Hệ thống hỏi đáp tự động hỗ trợ sinh viên ICTU, xây dựng trên `FastAPI` và kiến trúc `RAG` nhiều tầng. Dự án tập trung vào việc trả lời bám sát Knowledge Base nội bộ, hạn chế bịa thông tin, có khả năng route theo nhóm tri thức và hiển thị nguồn tham khảo cho người dùng.

## 1. Giới thiệu

### Bài toán

Sinh viên thường hỏi lặp lại các nội dung như:

- học phí, học bổng, miễn giảm;
- chương trình đào tạo, số tín chỉ;
- email sinh viên, hồ sơ, tốt nghiệp;
- sổ tay sinh viên, chính sách, quy định nhà trường.

Mục tiêu của dự án là xây một chatbot có thể:

- trả lời nhanh;
- ưu tiên dữ liệu trong tài liệu đã nạp;
- biết hỏi lại khi câu hỏi thiếu mốc áp dụng;
- hỗ trợ quản trị Knowledge Base ngay trên web.

### Điểm nổi bật của bản nâng cấp

- Chuẩn hóa cấu hình bằng `pydantic-settings` và `pathlib`.
- Bỏ phụ thuộc vào đường dẫn tuyệt đối kiểu `E:\new-test`.
- Tách rõ pipeline agent: `normalize_input -> classify_intent -> route_rag_tool -> retrieve_context -> generate_answer -> save_history`.
- Cải thiện hybrid retrieval giữa vector search và BM25.
- Thêm fallback an toàn khi không có context phù hợp.
- Bổ sung endpoint mới: `/health`, `/api/health`, `/api/chat`.
- UI chat hiển thị nguồn tham khảo và thời gian phản hồi.
- Bổ sung test cho agent pipeline, chat API và health API.

## 2. Công nghệ sử dụng

- `Python 3.11+`
- `FastAPI`
- `Uvicorn`
- `Jinja2`
- `SQLite`
- `ChromaDB`
- `rank-bm25`
- `sentence-transformers`
- `langchain-core`
- `langgraph`
- `slowapi`
- `httpx`

## 3. Kiến trúc tổng thể

### Luồng xử lý chính

1. Người dùng gửi câu hỏi từ Web UI hoặc API.
2. Agent chuẩn hóa input và phân loại intent.
3. Hệ thống route câu hỏi sang nhóm tri thức phù hợp:
   - `student_handbook_rag`
   - `school_policy_rag`
   - `student_faq_rag`
   - `fallback_rag`
4. Retriever lấy context từ:
   - vector store ChromaDB;
   - BM25 keyword search;
   - lexical fallback;
   - trusted web knowledge / web search khi cần dữ liệu mới.
5. Prompt builder tạo prompt bám sát context hiện tại.
6. LLM sinh câu trả lời hoặc bot hỏi lại nếu thiếu dữ kiện.
7. Hệ thống lưu lịch sử chat và metadata phục vụ truy vết.

### Các tầng mã nguồn chính

- `config/`
  - cấu hình môi trường, DB, middleware, app factory, prompt.
- `controllers/`
  - định nghĩa route web và API.
- `services/`
  - chứa logic chat agent, RAG, retrieval, vector store, web knowledge, moderation.
- `models/`
  - request/response model và dataclass kết quả retrieval.
- `views/`
  - response builder và giao diện Jinja2.
- `tests/`
  - unit test và smoke test cho các phần chính.
- `tools/`
  - script xử lý dữ liệu và hỗ trợ import corpus.

## 4. Cấu trúc thư mục

```text
.
├── config/
├── controllers/
├── data/
│   ├── bot-rule.md
│   ├── intents/
│   ├── primary_corpus/
│   ├── rag_uploads/
│   └── systemprompt.md
├── docs/
├── models/
├── services/
├── tests/
├── tools/
├── views/
├── main.py
├── readme.md
└── requirements.txt
```

## 5. Cài đặt

### Phiên bản Python (bắt buộc)

Dự án yêu cầu **Python 3.11 trở lên** (khớp `Dockerfile` và `pyproject.toml`). Python **3.9 không chạy được** toàn bộ codebase vì dùng `@dataclass(slots=True)` và một số dependency (ví dụ `click` trong `requirements.txt`) chỉ phân phối wheel cho Python ≥ 3.10.

- Cài [Python 3.11](https://www.python.org/downloads/) hoặc 3.12, rồi tạo venv bằng launcher Windows `py -3.11` như bên dưới.
- Nếu dùng **pyenv**: file `.python-version` trong repo đã ghi `3.11`.

### Tạo môi trường ảo

```powershell
py -3.11 -m venv venv
.\venv\Scripts\activate
```

### Cài dependencies

```powershell
pip install -r requirements.txt
```

Nếu bạn dùng tính năng web search riêng:

```powershell
pip install -r requirements-search.txt
```

## 6. Cấu hình `.env`

### Bước 1: tạo file `.env`

```powershell
Copy-Item .env.example .env
```

### Bước 2: điền các biến cần thiết

Các biến quan trọng nhất:

- `PARTNER_API_KEY`
- `JWT_SECRET`
- `SESSION_SECRET`
- `GROQ_API_KEY` hoặc cấu hình `OLLAMA_BASE_URL`
- `DB_PATH`
- `QA_CORPUS_ROOT`
- `RAG_UPLOAD_ROOT`
- `VECTORSTORE_DIR`

### Ghi chú về path

- Mọi path trong `.env` có thể để tương đối.
- Path tương đối sẽ được resolve từ thư mục gốc dự án.
- Dự án không còn phụ thuộc vào đường dẫn tuyệt đối trên máy cá nhân.

## 7. Chạy dự án

Lệnh chạy chuẩn:

```powershell
python -m uvicorn config.asgi:app --reload
```

Sau khi chạy:

- Web UI: `http://127.0.0.1:8000/`
- Chat page: `http://127.0.0.1:8000/chat`
- Health: `http://127.0.0.1:8000/health`
- API health: `http://127.0.0.1:8000/api/health`

## 8. API chính

### Public / tiện ích

- `GET /health`
- `GET /api/health`

### Chat API

- `POST /api/chat`
- `POST /api/v1/chat`

Request body:

```json
{
  "message": "Học phí năm học 2025-2026 là bao nhiêu?",
  "session_id": "demo-session",
  "llm_model": "auto"
}
```

### Auth

- `POST /api/auth/token`
- `POST /api/v1/auth/token`

### Admin / dữ liệu

- `POST /api/v1/upload`
- `GET /api/v1/knowledge-base`
- `GET /api/v1/metrics/rate-limit-429`

## 9. Nạp Knowledge Base

### Cách 1: nạp seed corpus có sẵn

Trên giao diện:

- vào `/data-loader`
- dùng chức năng import corpus

Hoặc dùng script hiện có nếu cần:

```powershell
python tools\data_pipeline\import_qa_generated_fixed.py
```

### Cách 2: upload file mới

Hệ thống hỗ trợ:

- `.md`
- `.markdown`
- `.txt`

File sẽ được:

1. lưu vào thư mục upload theo nhóm RAG;
2. chunk bằng chiến lược heading-aware;
3. index vào vector store;
4. rebuild BM25 để hybrid retrieval dùng ngay.

## 10. Giao diện và quản trị

### Trang người dùng

- `/chat`

Hiện tại giao diện chat hiển thị:

- câu hỏi người dùng;
- câu trả lời bot;
- nguồn tham khảo;
- thời gian phản hồi;
- model đã dùng.

### Trang quản trị

- `/data-loader`
- `/vector-manager`
- `/knowledge-base`
- `/config`
- `/history`

## 11. Chạy test

### Lệnh chuẩn

```powershell
pytest
```

### Lệnh đã xác minh trong môi trường hiện tại

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

Test hiện bao phủ:

- routing intent / RAG;
- retrieval và lexical fallback;
- upload / re-ingest pipeline;
- knowledge base;
- health API;
- chat API alias mới;
- security / CSRF / auth;
- config / middleware / DB migration.

## 12. Ảnh cần chụp để đưa vào báo cáo

Khuyến nghị chụp các màn hình sau:

1. Trang `/chat` với một câu hỏi có nguồn tham khảo.
2. Trang `/chat` với câu hỏi thiếu thông tin và bot hỏi lại.
3. Trang `/knowledge-base`.
4. Trang `/vector-manager`.
5. Trang `/config`.
6. Trang `/history`.

Bạn có thể đặt ảnh vào:

- `assets/`
- hoặc `docs/images/` nếu muốn quản lý riêng cho báo cáo.

## 13. Lưu ý triển khai

- Không commit `.env` thật lên repo.
- Production bắt buộc phải thay `PARTNER_API_KEY`, `JWT_SECRET`, `SESSION_SECRET`.
- Nếu không có backend LLM, chatbot vẫn có thể boot, nhưng sẽ trả lời fallback an toàn thay vì sinh nội dung từ model.

## 14. Tài liệu liên quan

- `CHANGELOG.md`
- `docs/technical_summary.md`
- `docs/demo_script.md`
- `docs/ai_agent_design.md`
- `docs/rag_regression_and_ops.md`
