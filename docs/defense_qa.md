# Q&A bảo vệ đồ án

## 1. Đề tài của em giải quyết bài toán gì?

Hệ thống hỗ trợ sinh viên ICTU tra cứu thông tin học vụ, chính sách, tuyển sinh và các câu hỏi thường gặp bằng chatbot. Mục tiêu là giảm thời gian tìm kiếm thủ công và tăng khả năng tiếp cận thông tin chính thống.

## 2. Vì sao em không làm chatbot gọi LLM trực tiếp?

Nếu gọi LLM trực tiếp thì câu trả lời dễ bị bịa hoặc không bám dữ liệu của trường. Vì vậy em dùng RAG để bot ưu tiên trả lời từ Knowledge Base nội bộ trước khi sinh câu trả lời.

## 3. Vì sao em chọn FastAPI?

FastAPI phù hợp để xây dựng API nhanh, rõ ràng, có validation tốt, dễ test và dễ tích hợp frontend cũng như các service AI phía sau.

## 4. Kiến trúc tổng thể của hệ thống là gì?

Kiến trúc hiện tại là `config -> controllers -> services -> views -> tests`. Trong đó:

- `config` quản lý cấu hình, app factory, middleware, database.
- `controllers` khai báo route FastAPI.
- `services` xử lý nghiệp vụ chat, RAG, retrieval, intent.
- `views` xử lý response API và giao diện.
- `tests` kiểm thử các luồng chính.

## 5. Pipeline xử lý một câu hỏi diễn ra như thế nào?

Luồng xử lý gồm 6 bước:

1. `normalize_input`
2. `classify_intent`
3. `route_rag_tool`
4. `retrieve_context`
5. `generate_answer`
6. `save_history`

Điểm mạnh là từng bước tách riêng nên dễ log, dễ kiểm thử và dễ giải thích với hội đồng.

## 6. Vì sao em tách nhiều nhóm tri thức?

Em tách để câu hỏi được định tuyến đúng nguồn, ví dụ nhóm tuyển sinh, nhóm chính sách, nhóm sổ tay sinh viên. Cách này giúp retrieval chính xác hơn và giảm việc lấy nhầm context không liên quan.

## 7. Hybrid retrieval là gì và vì sao cần?

Hybrid retrieval là kết hợp vector search và BM25.

- Vector search phù hợp với câu hỏi diễn đạt tự nhiên.
- BM25 phù hợp với từ khóa đặc thù, tên quy định, mã học phần, số tín chỉ.

Khi kết hợp hai cách, khả năng tìm đúng tài liệu sẽ tốt hơn dùng một cách đơn lẻ.

## 8. Làm sao hệ thống giảm hallucination?

- Bot ưu tiên context từ Knowledge Base.
- Có fallback khi không tìm thấy context phù hợp.
- Có trả về nguồn tham khảo nếu có.
- Nếu câu hỏi thiếu dữ kiện thì bot hỏi lại thay vì tự đoán.

## 9. Nếu dữ liệu không có thì hệ thống làm gì?

Hệ thống trả lời theo hướng an toàn, thông báo chưa tìm thấy thông tin phù hợp trong Knowledge Base hiện tại và khuyến nghị người dùng cung cấp thêm chi tiết hoặc kiểm tra nguồn chính thức.

## 10. Nếu người dùng hỏi mơ hồ thì sao?

Bot không cố trả lời ngay. Bot sẽ yêu cầu làm rõ thêm, ví dụ thiếu năm học, khóa, học kỳ hoặc đợt tuyển sinh.

## 11. Dữ liệu được lưu ở đâu?

- Lịch sử hội thoại và một số metadata được lưu bằng `SQLite`.
- Dữ liệu tri thức phục vụ truy xuất được lưu trong `ChromaDB`.
- Chỉ mục BM25 được xây dựng từ nội dung tài liệu đã nạp vào hệ thống.

## 12. Em đã sửa những lỗi kỹ thuật nào?

- Bỏ hard-code đường dẫn tuyệt đối kiểu Windows.
- Dùng `pathlib` và biến môi trường để cấu hình đường dẫn.
- Bổ sung `.env.example`.
- Chuẩn hóa endpoint và thêm `/health`, `/api/chat`.
- Thống nhất error handling.
- Sửa và bổ sung test để chạy được bằng `pytest`.

## 13. Em đã kiểm thử hệ thống như thế nào?

Em viết và sửa test cho các phần quan trọng:

- intent routing
- retrieval
- fallback
- health API
- chat API

Nhờ đó có thể kiểm tra nhanh khi thay đổi code và giảm nguy cơ làm hỏng chức năng cũ.

## 14. Điểm mạnh lớn nhất của đồ án là gì?

Điểm mạnh lớn nhất là hệ thống có kiến trúc rõ ràng, dễ giải thích, có thể demo được luồng AI Agent và RAG một cách minh bạch, không chỉ là chatbot gọi model đơn thuần.

## 15. Hạn chế lớn nhất hiện tại là gì?

Hạn chế lớn nhất là chất lượng phụ thuộc nhiều vào độ đầy đủ của Knowledge Base. Nếu dữ liệu chưa tốt hoặc chưa cập nhật thì câu trả lời cũng bị giới hạn theo.

## 16. Nếu có thêm thời gian em sẽ phát triển gì?

- Nâng cấp bộ phân loại intent bằng dữ liệu thực tế.
- Bổ sung reranker tốt hơn cho retrieval.
- Xây dựng dashboard quản trị Knowledge Base.
- Thu thập phản hồi người dùng để cải thiện chất lượng trả lời.

## 17. Một câu kết ngắn nếu hội đồng hỏi “điểm mới của em là gì?”

Điểm em muốn nhấn mạnh là hệ thống đã được tổ chức theo hướng một nền tảng RAG có quy trình xử lý rõ ràng, có fallback an toàn, có kiểm thử tự động và có thể giải thích được về mặt kỹ thuật khi triển khai trong bối cảnh thực tế của nhà trường.
