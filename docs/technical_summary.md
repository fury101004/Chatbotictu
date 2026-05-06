# Technical Summary

## 1. Kiến trúc tổng thể

Hệ thống được tổ chức theo mô hình nhiều tầng:

- `controllers`: nhận request từ web/API.
- `services`: xử lý nghiệp vụ chat, retrieval, vector store, moderation, web knowledge.
- `config`: cấu hình môi trường, DB, middleware, prompt, app factory.
- `views`: Jinja2 templates và response builders.
- `models`: request/response model và dataclass kết quả retrieval.

App được khởi tạo từ `config.asgi:app` thông qua `config.app_factory.create_app()`.

## 2. Pipeline RAG

Pipeline hiện tại:

1. Nhận câu hỏi.
2. Chuẩn hóa input và session.
3. Route sang nhóm tri thức phù hợp.
4. Retrieve context.
5. Sinh câu trả lời hoặc fallback.
6. Lưu lịch sử và metadata truy vết.

Retriever hỗ trợ:

- vector retrieval với ChromaDB;
- BM25 keyword retrieval;
- lexical fallback trên corpus;
- web knowledge cache đáng tin cậy;
- web search ICTU khi câu hỏi có tính thời gian thực.

## 3. AI Agent Workflow

Workflow mới được tách rõ thành các bước:

### normalize_input

- làm sạch message;
- chuẩn hóa `session_id`;
- chuẩn hóa lựa chọn model;
- chặn input rỗng.

### classify_intent

- phát hiện greeting / quick reply;
- moderation với từ ngữ công kích;
- phân loại xem có cần đi vào RAG hay không.

### route_rag_tool

- route theo keyword và heuristic;
- giữ `fallback_rag` cho câu mơ hồ hoặc giao thoa nhiều nhóm.

### retrieve_context

- gọi retriever đúng theo nhóm tri thức;
- kết hợp vector + BM25;
- đánh dấu trường hợp thiếu context;
- phát hiện câu hỏi thiếu năm học / khóa / học kỳ / đợt để hỏi lại.

### generate_answer

- nếu ngoài phạm vi ICTU: trả lời guardrail;
- nếu thiếu thông tin: hỏi lại;
- nếu không có context: trả fallback an toàn;
- nếu có context: gọi LLM và ép bám sát ngữ cảnh.

### save_history

- lưu user message và bot response vào SQLite;
- lưu metadata retrieval vào session memory;
- nếu câu trả lời đến từ web search thì có thể cache vào trusted web knowledge.

## 4. Cơ sở dữ liệu

### SQLite

File mặc định: `data/bot_config.db`

Các bảng chính:

- `chat_history`
- `config`
- `uploaded_files`
- `uploaded_files_v2`
- `approved_chat_qa`
- `web_search_knowledge`

### Vector Database

- Dùng `ChromaDB PersistentClient`
- Thư mục mặc định: `vectorstore/`

Mỗi chunk lưu:

- nội dung chunk;
- source file;
- title/section;
- academic year;
- document type;
- tool name;
- metadata phục vụ ranking và hiển thị.

## 5. Hybrid Retrieval

Điểm nâng cấp chính:

- trước đây BM25 chỉ hỗ trợ chấm trên candidate lấy từ vector search;
- hiện tại candidate pool được lấy từ cả vector search và BM25;
- điểm vector và BM25 được chuẩn hóa rồi trộn lại;
- bot rule vẫn được giữ top priority.

Lợi ích:

- tăng khả năng bắt trúng câu hỏi có từ khóa rõ;
- giảm nguy cơ bỏ sót tài liệu đúng khi vector score yếu;
- hành vi retrieval dễ giải thích hơn khi bảo vệ.

## 6. Điểm mạnh

- Cấu hình portable, không phụ thuộc path tuyệt đối.
- Route tri thức rõ ràng theo nhóm nghiệp vụ.
- Fallback an toàn, hạn chế bịa thông tin.
- Có giao diện quản trị Knowledge Base.
- Có logging theo từng bước agent.
- Có test cho các luồng quan trọng.

## 7. Hạn chế

- Chất lượng trả lời vẫn phụ thuộc chất lượng corpus đã nạp.
- Web search chỉ nên xem là nguồn bổ trợ, không thay thế dữ liệu nội bộ.
- Nếu backend LLM không sẵn sàng, hệ thống chỉ trả lời được bằng rule/fallback.
- UI hiện tại thiên về tính năng hơn là dashboard phân tích chuyên sâu.

## 8. Hướng phát triển

- Bổ sung reranker chuyên dụng cho top-k retrieval.
- Thêm dashboard thống kê query, source hit rate và latency.
- Tách prompt/routing rule thành cấu hình dễ chỉnh cho admin.
- Thêm đánh giá tự động theo bộ câu hỏi vàng.
- Mở rộng upload sang PDF/DOCX với pipeline chuẩn hóa riêng.
