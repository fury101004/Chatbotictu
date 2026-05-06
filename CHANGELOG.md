# Changelog

## 2026-05-05

### Môi trường và cấu hình

- Chuẩn hóa cấu hình tập trung trong `config/settings.py`.
- Dùng `pathlib` và biến môi trường cho:
  - DB path
  - upload path
  - vector store path
  - prompt path
  - bot rule path
  - intents path
  - template/static path
- Thêm `.env.example` đầy đủ biến cấu hình.
- Bổ sung `pytest` vào `requirements.txt`.

### Ứng dụng FastAPI

- Giữ tương thích route cũ `/api/v1/...`.
- Thêm route mới:
  - `/health`
  - `/api/health`
  - `/api/chat`
  - `/api/auth/token`
- Bổ sung health payload có trạng thái cấu hình LLM và embedding backend.
- Thêm xử lý lỗi thống nhất cho API:
  - HTTP error
  - validation error
  - rate limit error
  - internal server error

### RAG và AI Agent

- Tách lại pipeline chat agent thành các bước rõ ràng:
  - `normalize_input`
  - `classify_intent`
  - `route_rag_tool`
  - `retrieve_context`
  - `generate_answer`
  - `save_history`
- Thêm log theo từng bước xử lý.
- Cải thiện hybrid retrieval:
  - lấy candidate từ cả vector search và BM25;
  - trộn điểm trên cùng một candidate pool;
  - đính kèm `hybrid_score`, `vector_score`, `bm25_score` vào metadata.
- Thêm fallback an toàn khi không tìm thấy context.
- Thêm cơ chế hỏi lại khi câu hỏi thiếu mốc như:
  - năm học
  - khóa
  - học kỳ
  - đợt áp dụng

### UI

- Giao diện chat hiển thị thêm:
  - nguồn tham khảo
  - thời gian phản hồi
  - model đã dùng

### Test

- Loại bỏ phụ thuộc vào đường dẫn tuyệt đối trong test.
- Thêm test cho:
  - chat agent clarification fallback
  - knowledge-base fallback
  - health endpoints
  - `/api/chat`

### Tài liệu

- Viết lại `readme.md`.
- Thêm `docs/technical_summary.md`.
- Thêm `docs/demo_script.md`.
