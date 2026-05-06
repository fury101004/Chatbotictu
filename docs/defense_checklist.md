# Checklist bảo vệ đồ án

## 1. Mở đầu 30 giây

Có thể giới thiệu ngắn như sau:

> Đề tài của em là xây dựng hệ thống hỏi đáp tự động hỗ trợ sinh viên ICTU trên nền tảng FastAPI kết hợp AI Agent và RAG. Hệ thống ưu tiên trả lời từ Knowledge Base nội bộ của nhà trường, có cơ chế hybrid retrieval giữa vector search và BM25, có fallback khi thiếu dữ liệu, và được kiểm thử bằng test tự động để đảm bảo độ ổn định.

## 2. Checklist trước khi demo

- Kiểm tra đã cài đúng môi trường từ `requirements.txt`.
- Kiểm tra file `.env` đã khai báo đủ biến cần thiết.
- Chạy ứng dụng bằng lệnh:

```bash
python -m uvicorn config.asgi:app --reload
```

- Mở giao diện chat và kiểm tra bot hiển thị được:
  - câu hỏi người dùng
  - câu trả lời bot
  - nguồn tham khảo
  - thời gian phản hồi
- Kiểm tra endpoint health:

```bash
GET /health
GET /api/health
```

- Chuẩn bị sẵn 3 câu hỏi demo:
  - 1 câu về tuyển sinh
  - 1 câu về chính sách sinh viên
  - 1 câu ngoài dữ liệu để demo fallback

## 3. Nếu hội đồng hỏi về kiến trúc

Trả lời ngắn gọn:

- Backend dùng `FastAPI`, entrypoint chạy qua `config.asgi:app`.
- Kiến trúc tách lớp rõ ràng: `config -> controllers -> services -> views -> tests`.
- Phần nghiệp vụ chính nằm ở `services/`.
- Dữ liệu hội thoại và metadata lưu bằng `SQLite`.
- Dữ liệu tri thức được truy xuất qua `ChromaDB` kết hợp `BM25`.
- Giao diện web là chat UI đơn giản để phục vụ demo và kiểm thử nhanh.

## 4. Nếu hội đồng hỏi về pipeline RAG

Có thể trả lời theo đúng luồng hiện tại:

1. `normalize_input`: chuẩn hóa câu hỏi đầu vào.
2. `classify_intent`: nhận diện mục đích câu hỏi.
3. `route_rag_tool`: định tuyến câu hỏi vào đúng nhóm tri thức.
4. `retrieve_context`: lấy ngữ cảnh bằng hybrid retrieval.
5. `generate_answer`: sinh câu trả lời từ context đã truy xuất.
6. `save_history`: lưu lịch sử hội thoại để theo dõi và mở rộng sau này.

Điểm nên nhấn mạnh:

- Bot ưu tiên dùng dữ liệu từ Knowledge Base.
- Nếu không đủ dữ liệu, bot không bịa mà trả lời theo hướng an toàn.
- Nếu câu hỏi thiếu thông tin quan trọng, bot sẽ hỏi lại.

## 5. Nếu hội đồng hỏi vì sao dùng hybrid retrieval

Trả lời ngắn:

- Vector search mạnh khi câu hỏi diễn đạt tự nhiên hoặc khác từ khóa gốc.
- BM25 mạnh khi câu hỏi chứa từ khóa đặc thù như tên quy chế, tín chỉ, học bổng, điều kiện xét.
- Kết hợp hai cách giúp tăng recall và giảm bỏ sót tài liệu quan trọng.
- Trong hệ thống hiện tại, kết quả được hợp nhất để chọn context phù hợp hơn trước khi gọi LLM.

## 6. Nếu hội đồng hỏi làm sao giảm hallucination

Có thể trả lời:

- Prompt được thiết kế để ưu tiên Knowledge Base nội bộ.
- Chỉ dùng context đã retrieve để trả lời.
- Có fallback khi không tìm thấy context phù hợp.
- Có trả về nguồn tham khảo để người dùng đối chiếu.
- Với câu hỏi thiếu dữ kiện, bot hỏi lại thay vì suy đoán.

## 7. Nếu hội đồng hỏi AI Agent có gì khác chatbot thường

Trả lời:

- Chatbot thường chỉ nhận câu hỏi rồi gọi model trả lời trực tiếp.
- Trong đồ án này, agent được tách thành các bước rõ ràng nên dễ kiểm soát, dễ log, dễ giải thích.
- Mỗi bước đều có vai trò riêng như chuẩn hóa, định tuyến, retrieve, sinh câu trả lời và lưu lịch sử.
- Cách tách này phù hợp với yêu cầu bảo trì và mở rộng trong môi trường thực tế.

## 8. Nếu hội đồng hỏi em đã nâng cấp gì

Bạn có thể liệt kê:

- Sửa cấu hình môi trường, bỏ hard-code đường dẫn tuyệt đối.
- Chuẩn hóa project để chạy bằng `python -m uvicorn config.asgi:app --reload`.
- Bổ sung `.env.example`.
- Nâng cấp hybrid retrieval giữa ChromaDB và BM25.
- Bổ sung fallback và cơ chế hỏi lại khi thiếu thông tin.
- Thêm API `/health` và `/api/chat`.
- Chuẩn hóa error handling.
- Nâng cấp giao diện chat để hiển thị nguồn và thời gian phản hồi.
- Sửa và bổ sung test để chạy bằng `pytest`.
- Viết lại tài liệu kỹ thuật và kịch bản demo.

## 9. Nếu hội đồng hỏi điểm mạnh của hệ thống

- Kiến trúc rõ ràng, dễ đọc, dễ bảo trì.
- Có thể giải thích pipeline AI từng bước.
- Ưu tiên tri thức nội bộ thay vì trả lời tự do.
- Có kiểm thử tự động cho các chức năng quan trọng.
- Phù hợp với bài toán hỏi đáp trong phạm vi trường đại học.

## 10. Nếu hội đồng hỏi hạn chế

Nên trả lời trung thực:

- Chất lượng trả lời vẫn phụ thuộc vào độ đầy đủ và chất lượng của Knowledge Base.
- Intent routing hiện tại vẫn chủ yếu theo luật và heuristic, chưa phải bộ phân loại học sâu chuyên biệt.
- Chưa có dashboard quản trị nâng cao cho việc đánh giá chất lượng câu trả lời theo thời gian.
- Nếu mở rộng quy mô lớn hơn, cần tối ưu thêm khả năng quan sát hệ thống, cache và quản lý dữ liệu tri thức.

## 11. Nếu hội đồng hỏi hướng phát triển

- Tăng chất lượng phân loại intent bằng dữ liệu thật từ sinh viên.
- Bổ sung reranking mạnh hơn cho retrieval.
- Xây dựng trang quản trị Knowledge Base đầy đủ hơn.
- Thêm đánh giá phản hồi người dùng để cải thiện dữ liệu.
- Tích hợp xác thực sinh viên để cá nhân hóa câu trả lời theo đối tượng.

## 12. Câu kết 20 giây

> Điểm em muốn nhấn mạnh là hệ thống không chỉ dừng ở chatbot gọi model, mà đã được tổ chức theo hướng một hệ thống RAG có kiến trúc rõ ràng, có kiểm thử, có khả năng mở rộng và có thể giải thích được trước hội đồng cũng như khi triển khai thực tế.
