# Demo Script 5 Phút

## Mục tiêu demo

Chứng minh hệ thống:

- chạy ổn định;
- trả lời bám theo Knowledge Base;
- biết hiển thị nguồn;
- biết hỏi lại hoặc fallback khi thiếu dữ liệu;
- có trang quản trị Knowledge Base để giải thích phần vận hành.

## Chuẩn bị trước demo

- Chạy server bằng lệnh:

```powershell
python -m uvicorn config.asgi:app --reload
```

- Mở sẵn các tab:
  - `/chat`
  - `/knowledge-base`
  - `/vector-manager`

## Kịch bản chi tiết

### 1. Mở hệ thống

Thời lượng: 30-40 giây

Lời dẫn gợi ý:

> Đây là hệ thống hỏi đáp tự động hỗ trợ sinh viên ICTU. Hệ thống được xây dựng trên FastAPI và RAG, có khả năng route câu hỏi theo từng nhóm tri thức như sổ tay sinh viên, quy định chính sách và FAQ nghiệp vụ.

Hành động:

- mở trang `/chat`;
- giới thiệu nhanh giao diện;
- chỉ ra bot có hiển thị model, thời gian phản hồi và nguồn tham khảo.

### 2. Hỏi câu tuyển sinh / chương trình đào tạo

Thời lượng: 60 giây

Câu hỏi gợi ý:

> Chương trình đào tạo ngành Công nghệ thông tin khóa 24 có bao nhiêu tín chỉ?

Điểm cần nói:

- bot route về nhóm `student_handbook_rag`;
- bot lấy context từ Knowledge Base đã nạp;
- nếu có nguồn, giao diện hiển thị ngay bên dưới câu trả lời.

### 3. Hỏi câu chính sách sinh viên

Thời lượng: 60 giây

Câu hỏi gợi ý:

> Điều kiện để được miễn giảm học phí là gì?

Điểm cần nói:

- bot route sang nhóm `school_policy_rag`;
- câu trả lời ưu tiên dữ liệu nội bộ, không tự bịa;
- nếu câu hỏi thiếu năm học/đợt áp dụng, bot có thể hỏi lại để tránh trả lời sai.

### 4. Hỏi câu không có dữ liệu

Thời lượng: 45-60 giây

Câu hỏi gợi ý:

> ICTU có chính sách hỗ trợ du học sinh ở Phần Lan trong học kỳ mùa đông không?

Điểm cần nói:

- nếu KB không có context phù hợp, bot không bịa thông tin;
- hệ thống trả fallback an toàn hoặc hỏi lại để làm rõ;
- đây là điểm quan trọng để bảo đảm độ tin cậy.

### 5. Demo trang quản trị Knowledge Base

Thời lượng: 60-75 giây

Hành động:

- mở `/knowledge-base`;
- cho thấy có thể duyệt các cặp hỏi đáp gần đây;
- mở `/vector-manager`;
- giải thích mỗi tài liệu được chunk, index vào vector store và dùng cho retrieval.

Lời dẫn gợi ý:

> Ngoài giao diện chat, hệ thống còn có phần quản trị Knowledge Base. Tại đây có thể xem tài liệu đã nạp, các chunk được index và các cặp hỏi đáp đã được duyệt để đưa ngược vào hệ thống retrieval.

## Chốt demo

Thời lượng: 20-30 giây

Kết luận gợi ý:

> Tóm lại, hệ thống không chỉ trả lời câu hỏi mà còn có kiến trúc RAG tương đối hoàn chỉnh: route tri thức, retrieval hybrid, fallback an toàn, lưu lịch sử và quản trị Knowledge Base. Đây là nền tảng có thể tiếp tục mở rộng cho các bài toán hỗ trợ sinh viên thực tế.
