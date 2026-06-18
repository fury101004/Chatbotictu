---
title: "ICTU 30-question evaluation knowledge base"
generated_at: "2026-05-20T18:11:27+07:00"
source_type: "evaluation"
tool_name: "student_faq_rag"
generator: "tools/evaluation/evaluate_ictu_30_questions.py"
---

# ICTU 30-question evaluation knowledge base

## Tóm tắt

- Tổng số câu kiểm thử: 30.
- 15 câu kiểm dữ liệu nội bộ, 15 câu kiểm luồng web search.
- Overall accuracy: 96.67%.
- Route accuracy: 100.00%.
- Flow accuracy: 100.00%.
- Source hit rate: 93.33%.
- Web search configured khi chạy: True.
- Live web enabled khi chạy: True.
- Use LLM router khi chạy: False.

## Bộ câu hỏi và kết quả

### local_001 - local_data

**Câu hỏi:** Sổ tay sinh viên 2025-2026 áp dụng cho đối tượng nào?

**Kết quả:** Đạt

- Expected tool: `student_handbook_rag`
- Predicted tool: `student_handbook_rag`
- Expected flow: `local_data`
- Predicted flow: `local_data` / `local_first`
- Retrieval mode: `student_handbook_rag`
- Chunks used: `1`
- Sources: student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md

**Trích ngữ cảnh truy xuất:**

[Question Set - 8. SO TAY SINH VIEN 2025-2026 | source: student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md | score: 151] **Question:** Sổ tay sinh viên 2025-2026 áp dụng cho đối tượng nào? **Answer:** Sổ tay sinh viên 2025-2026 là tài liệu lưu hành nội bộ dành cho sinh viên khóa 24 của Trường Đại học Công nghệ Thông tin và Truyền thông - Đại học Thái Nguyên.

### local_002 - local_data

**Câu hỏi:** Sinh viên khóa 24 dùng sổ tay sinh viên năm học nào?

**Kết quả:** Đạt

- Expected tool: `student_handbook_rag`
- Predicted tool: `student_handbook_rag`
- Expected flow: `local_data`
- Predicted flow: `local_data` / `local_first`
- Retrieval mode: `student_handbook_rag`
- Chunks used: `1`
- Sources: student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md

**Trích ngữ cảnh truy xuất:**

[Question Set - 8. SO TAY SINH VIEN 2025-2026 | source: student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md | score: 144] **Question:** Sổ tay sinh viên 2025-2026 áp dụng cho đối tượng nào? **Answer:** Sổ tay sinh viên 2025-2026 là tài liệu lưu hành nội bộ dành cho sinh viên khóa 24 của Trường Đại học Công nghệ Thông tin và Truyền thông - Đại học Thái Nguyên.

### local_003 - local_data

**Câu hỏi:** Trong sổ tay 2025-2026, giá trị cốt lõi của Trường là gì?

**Kết quả:** Đạt

- Expected tool: `student_handbook_rag`
- Predicted tool: `student_handbook_rag`
- Expected flow: `local_data`
- Predicted flow: `local_data` / `local_first`
- Retrieval mode: `student_handbook_rag`
- Chunks used: `1`
- Sources: student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md

**Trích ngữ cảnh truy xuất:**

[Question Set - 8. SO TAY SINH VIEN 2025-2026 | source: student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md | score: 130] **Question:** Giá trị cốt lõi của Trường là gì? **Answer:** Giá trị cốt lõi, giá trị văn hóa của Trường là Đoàn kết - Tận tâm - Sáng tạo - Thực tiễn.

### local_004 - local_data

**Câu hỏi:** Trong sổ tay 2025-2026, triết lý giáo dục của Trường được nêu như thế nào?

**Kết quả:** Đạt

- Expected tool: `student_handbook_rag`
- Predicted tool: `student_handbook_rag`
- Expected flow: `local_data`
- Predicted flow: `local_data` / `local_first`
- Retrieval mode: `student_handbook_rag`
- Chunks used: `1`
- Sources: student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md

**Trích ngữ cảnh truy xuất:**

[Question Set - 8. SO TAY SINH VIEN 2025-2026 | source: student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md | score: 142] **Question:** Triết lý giáo dục của Trường được nêu như thế nào? **Answer:** Triết lý giáo dục là giáo dục toàn diện lấy người học làm trung tâm; đào tạo hình mẫu công dân số, kiến tạo tương lai và nuôi dưỡng lòng nhân ái.

### local_005 - local_data

**Câu hỏi:** Sổ tay 2025-2026 nêu địa chỉ và thông tin liên hệ của Trường là gì?

**Kết quả:** Đạt

- Expected tool: `student_handbook_rag`
- Predicted tool: `student_handbook_rag`
- Expected flow: `local_data`
- Predicted flow: `local_data` / `local_first`
- Retrieval mode: `student_handbook_rag`
- Chunks used: `1`
- Sources: student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md

**Trích ngữ cảnh truy xuất:**

[Question Set - 8. SO TAY SINH VIEN 2025-2026 | source: student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md | score: 153] **Question:** Địa chỉ và thông tin liên hệ của Trường là gì? **Answer:** Trường Đại học Công nghệ Thông tin và Truyền thông - Đại học Thái Nguyên có địa chỉ tại phường Quyết Thắng, tỉnh Thái Nguyên; điện thoại 0208.3846254; fax 0208.3846237; email contact@ictu.edu.vn; website www.ictu.edu ...

### local_006 - local_data

**Câu hỏi:** Quy định về công tác người học áp dụng cho ai?

**Kết quả:** Đạt

- Expected tool: `student_handbook_rag`
- Predicted tool: `student_handbook_rag`
- Expected flow: `local_data`
- Predicted flow: `local_data` / `local_first`
- Retrieval mode: `student_handbook_rag`
- Chunks used: `4`
- Sources: student_handbooks/6. SO TAY SINH VIEN 2023-2024.questions.md, student_handbooks/7. SO TAY SINH VIEN 2024-2025.questions.md, student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md

**Trích ngữ cảnh truy xuất:**

[Question Set - 6. SO TAY SINH VIEN 2023-2024 | source: student_handbooks/6. SO TAY SINH VIEN 2023-2024.questions.md | score: 106] **Question:** Quy định về công tác người học áp dụng cho ai? **Answer:** Quy định áp dụng đối với người học đang học tập, nghiên cứu và rèn luyện tại Trường Đại học Công nghệ Thông tin và Truyền thông. [Question Set - 7. SO TAY SINH VIEN 2024-2025 | source: student_handbooks/7. SO TAY SIN ...

### local_007 - local_data

**Câu hỏi:** Mục đích của công tác người học là gì?

**Kết quả:** Đạt

- Expected tool: `student_handbook_rag`
- Predicted tool: `student_handbook_rag`
- Expected flow: `local_data`
- Predicted flow: `local_data` / `local_first`
- Retrieval mode: `student_handbook_rag`
- Chunks used: `3`
- Sources: student_handbooks/6. SO TAY SINH VIEN 2023-2024.questions.md, student_handbooks/7. SO TAY SINH VIEN 2024-2025.questions.md, student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md

**Trích ngữ cảnh truy xuất:**

[Question Set - 6. SO TAY SINH VIEN 2023-2024 | source: student_handbooks/6. SO TAY SINH VIEN 2023-2024.questions.md | score: 98] **Question:** Mục đích của công tác người học là gì? **Answer:** Công tác người học nhằm bảo đảm thực hiện mục tiêu giáo dục theo Luật Giáo dục hiện hành và bảo đảm người học được hưởng quyền, thực hiện nhiệm vụ trong Đại học Thái Nguyên và trong Trường. [Question Set - 7. SO TAY SINH VIEN ...

### local_008 - local_data

**Câu hỏi:** Người học tại ICTU có nhiệm vụ gì?

**Kết quả:** Đạt

- Expected tool: `student_handbook_rag`
- Predicted tool: `student_handbook_rag`
- Expected flow: `local_data`
- Predicted flow: `local_data` / `local_first`
- Retrieval mode: `student_handbook_rag`
- Chunks used: `8`
- Sources: student_handbooks/1. SO TAY SINH VIEN 2018-2019.questions.md, student_handbooks/2. SO TAY SINH VIEN 2019-2020.questions.md, student_handbooks/3. SO TAY SINH VIEN 2020-2021.questions.md

**Trích ngữ cảnh truy xuất:**

[Question Set - 1. SO TAY SINH VIEN 2018-2019 | source: student_handbooks/1. SO TAY SINH VIEN 2018-2019.questions.md | score: 69] **Question:** Sinh viên có những nhiệm vụ chính nào? **Answer:** Sinh viên phải chấp hành chủ trương, chính sách, pháp luật, điều lệ và quy chế của Trường; học tập và rèn luyện theo kế hoạch; tôn trọng nhà giáo, cán bộ, viên chức; giữ gìn tài sản; khám sức khỏe theo quy định; đóng học phí ...

### local_009 - local_data

**Câu hỏi:** Người học được hưởng những quyền gì?

**Kết quả:** Đạt

- Expected tool: `student_handbook_rag`
- Predicted tool: `student_handbook_rag`
- Expected flow: `local_data`
- Predicted flow: `local_data` / `local_first`
- Retrieval mode: `student_handbook_rag`
- Chunks used: `8`
- Sources: student_handbooks/6. SO TAY SINH VIEN 2023-2024.questions.md, student_handbooks/7. SO TAY SINH VIEN 2024-2025.questions.md, student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md

**Trích ngữ cảnh truy xuất:**

[Question Set - 6. SO TAY SINH VIEN 2023-2024 | source: student_handbooks/6. SO TAY SINH VIEN 2023-2024.questions.md | score: 75] **Question:** Người học không được làm những hành vi nào? **Answer:** Người học không được thực hiện các hành vi pháp luật cấm, trái đạo đức xã hội; xâm phạm lợi ích quốc gia, dân tộc, quyền và lợi ích hợp pháp của người khác; tổ chức hoặc tham gia hoạt động trái pháp luật; gian lận trong ...

### local_010 - local_data

**Câu hỏi:** Người học không được làm những hành vi nào?

**Kết quả:** Đạt

- Expected tool: `student_handbook_rag`
- Predicted tool: `student_handbook_rag`
- Expected flow: `local_data`
- Predicted flow: `local_data` / `local_first`
- Retrieval mode: `student_handbook_rag`
- Chunks used: `8`
- Sources: student_handbooks/6. SO TAY SINH VIEN 2023-2024.questions.md, student_handbooks/7. SO TAY SINH VIEN 2024-2025.questions.md, student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md

**Trích ngữ cảnh truy xuất:**

[Question Set - 6. SO TAY SINH VIEN 2023-2024 | source: student_handbooks/6. SO TAY SINH VIEN 2023-2024.questions.md | score: 103] **Question:** Người học không được làm những hành vi nào? **Answer:** Người học không được thực hiện các hành vi pháp luật cấm, trái đạo đức xã hội; xâm phạm lợi ích quốc gia, dân tộc, quyền và lợi ích hợp pháp của người khác; tổ chức hoặc tham gia hoạt động trái pháp luật; gian lận trong ...

### local_011 - local_data

**Câu hỏi:** Điều kiện đạt danh hiệu sinh viên Khá, Giỏi, Xuất sắc là gì?

**Kết quả:** Đạt

- Expected tool: `student_handbook_rag`
- Predicted tool: `student_handbook_rag`
- Expected flow: `local_data`
- Predicted flow: `local_data` / `local_first`
- Retrieval mode: `student_handbook_rag`
- Chunks used: `5`
- Sources: student_handbooks/1. SO TAY SINH VIEN 2018-2019.questions.md, student_handbooks/2. SO TAY SINH VIEN 2019-2020.questions.md, student_handbooks/3. SO TAY SINH VIEN 2020-2021.questions.md

**Trích ngữ cảnh truy xuất:**

[Question Set - 1. SO TAY SINH VIEN 2018-2019 | source: student_handbooks/1. SO TAY SINH VIEN 2018-2019.questions.md | score: 124] **Question:** Điều kiện đạt danh hiệu sinh viên Khá, Giỏi, Xuất sắc là gì? **Answer:** Sinh viên Khá cần kết quả học tập từ 2,50 đến 3,19 theo thang điểm 4 và rèn luyện từ khá trở lên; sinh viên Giỏi cần kết quả học tập từ 3,20 đến 3,59 và rèn luyện từ tốt trở lên; sinh viên Xuất sắc cần ...

### local_012 - local_data

**Câu hỏi:** Sinh viên học lực bình thường phải đăng ký tối thiểu bao nhiêu tín chỉ mỗi học kỳ chính?

**Kết quả:** Đạt

- Expected tool: `student_handbook_rag`
- Predicted tool: `student_handbook_rag`
- Expected flow: `local_data`
- Predicted flow: `local_data` / `local_first`
- Retrieval mode: `student_handbook_rag`
- Chunks used: `5`
- Sources: student_handbooks/1. SO TAY SINH VIEN 2018-2019.questions.md, student_handbooks/2. SO TAY SINH VIEN 2019-2020.questions.md, student_handbooks/3. SO TAY SINH VIEN 2020-2021.questions.md

**Trích ngữ cảnh truy xuất:**

[Question Set - 1. SO TAY SINH VIEN 2018-2019 | source: student_handbooks/1. SO TAY SINH VIEN 2018-2019.questions.md | score: 156] **Question:** Sinh viên học lực bình thường phải đăng ký tối thiểu bao nhiêu tín chỉ mỗi học kỳ chính? **Answer:** Sinh viên học lực bình thường phải đăng ký tối thiểu 14 tín chỉ mỗi học kỳ chính, trừ học kỳ cuối khóa. [Question Set - 2. SO TAY SINH VIEN 2019-2020 | source: student_handbo ...

### local_013 - local_data

**Câu hỏi:** Sinh viên học lực yếu được đăng ký bao nhiêu tín chỉ?

**Kết quả:** Đạt

- Expected tool: `student_handbook_rag`
- Predicted tool: `student_handbook_rag`
- Expected flow: `local_data`
- Predicted flow: `local_data` / `local_first`
- Retrieval mode: `student_handbook_rag`
- Chunks used: `8`
- Sources: student_handbooks/1. SO TAY SINH VIEN 2018-2019.questions.md, student_handbooks/2. SO TAY SINH VIEN 2019-2020.questions.md, student_handbooks/3. SO TAY SINH VIEN 2020-2021.questions.md

**Trích ngữ cảnh truy xuất:**

[Question Set - 1. SO TAY SINH VIEN 2018-2019 | source: student_handbooks/1. SO TAY SINH VIEN 2018-2019.questions.md | score: 136] **Question:** Sinh viên học lực yếu được đăng ký bao nhiêu tín chỉ? **Answer:** Sinh viên đang bị xếp hạng học lực yếu phải đăng ký tối thiểu 10 tín chỉ mỗi học kỳ chính và chỉ được đăng ký tối đa 14 tín chỉ mỗi học kỳ chính, trừ học kỳ cuối khóa. [Question Set - 2. SO TAY SINH VIEN 2019- ...

### local_014 - local_data

**Câu hỏi:** Học kỳ phụ được đăng ký tối đa bao nhiêu tín chỉ?

**Kết quả:** Đạt

- Expected tool: `student_handbook_rag`
- Predicted tool: `student_handbook_rag`
- Expected flow: `local_data`
- Predicted flow: `local_data` / `local_first`
- Retrieval mode: `student_handbook_rag`
- Chunks used: `8`
- Sources: student_handbooks/1. SO TAY SINH VIEN 2018-2019.questions.md, student_handbooks/2. SO TAY SINH VIEN 2019-2020.questions.md, student_handbooks/3. SO TAY SINH VIEN 2020-2021.questions.md

**Trích ngữ cảnh truy xuất:**

[Question Set - 1. SO TAY SINH VIEN 2018-2019 | source: student_handbooks/1. SO TAY SINH VIEN 2018-2019.questions.md | score: 122] **Question:** Học kỳ phụ được đăng ký tối đa bao nhiêu tín chỉ? **Answer:** Khối lượng học tập tối đa ở học kỳ phụ là 10 tín chỉ và không quy định khối lượng học tập tối thiểu. [Question Set - 2. SO TAY SINH VIEN 2019-2020 | source: student_handbooks/2. SO TAY SINH VIEN 2019-2020.question ...

### local_015 - local_data

**Câu hỏi:** Sinh viên cần nộp chứng chỉ trước đợt xét tốt nghiệp bao lâu?

**Kết quả:** Cần xem lại

- Expected tool: `student_faq_rag`
- Predicted tool: `student_faq_rag`
- Expected flow: `local_data`
- Predicted flow: `local_data` / `local_first`
- Retrieval mode: `student_faq_rag`
- Chunks used: `1`
- Sources: uploads/student_faq_rag/_knowledge_base_chat/approved-chat-78-khoa-24-nay-can-bao-nhieu-tin-chi-de-tot-nghiep-.md

**Trích ngữ cảnh truy xuất:**

[Approved Chat QA - khóa 24 này cần bao nhiêu tín chỉ để tốt nghiệp cử nhân? | source: uploads/student_faq_rag/_knowledge_base_chat/approved-chat-78-khoa-24-nay-can-bao-nhieu-tin-chi-de-tot-nghiep-.md | score: 71] # Approved Chat QA - khóa 24 này cần bao nhiêu tín chỉ để tốt nghiệp cử nhân? ## Câu hỏi khóa 24 này cần bao nhiêu tín chỉ để tốt nghiệp cử nhân? ## Trả lời đã duyệt **Ý chính:** Để tốt nghiệp cử nhân, sinh ...

### web_001 - web_search

**Câu hỏi:** ICTU hôm nay có thông báo mới nhất gì cho sinh viên?

**Kết quả:** Đạt

- Expected tool: `any`
- Predicted tool: `fallback_rag`
- Expected flow: `web_search`
- Predicted flow: `web_search` / `web_first`
- Retrieval mode: `web_search`
- Chunks used: `4`
- Sources: https://fet.ictu.edu.vn/category/thong-bao/thong-bao-sinh-vien/, https://fet.ictu.edu.vn/tuyen-sinh-thac-si-nam-2026-co-hoi-hoc-truoc-danh-cho-sinh-vien-ictu/, https://ictu.edu.vn/ictu-to-chuc-le-ky-niem-ngay-nha-giao-viet-nam-20-11-tri-an-ket-noi-lan-toa/

**Trích ngữ cảnh truy xuất:**

[Web search ICTU | title: ThôngbáoSinhviên- Khoa Kỹ Thuật và Công nghệ | source: https://fet.ictu.edu.vn/category/thong-bao/thong-bao-sinh-vien/] Nhằm thúc đẩy phong trào nghiên cứu khoa học và sáng tạo trong sinh viên, Khoa Kỹ thuật và Công nghệ chính thức phát động cuộc thi “IoT Challenge 2025” với chủ đề “Smart Future of Things” – Tương lai thông minh. Đây là cơ... Thông báo Sinh viên Đây chính là nội dung chính c ...

### web_002 - web_search

**Câu hỏi:** ICTU tuyển sinh năm nay có thông tin mới nhất nào?

**Kết quả:** Đạt

- Expected tool: `any`
- Predicted tool: `fallback_rag`
- Expected flow: `web_search`
- Predicted flow: `web_search` / `web_first`
- Retrieval mode: `web_search`
- Chunks used: `4`
- Sources: https://ictu.edu.vn/, https://tuyensinh.ictu.edu.vn/ttts2025/, http://ect.ictu.edu.vn/

**Trích ngữ cảnh truy xuất:**

[Web search ICTU | title: Trường Đại học Công NghệThôngTinvà TruyềnThông | source: https://ictu.edu.vn/] Ngày 14/12/2001, Khoa Công nghệ thông tin trực thuộc Đại học Thái Nguyên được thành lập theo quyết định 6946/QĐ-BGDĐT-TCCB của Bộ trưởng Bộ Giáo dục và Đào tạo. Năm 2005 đánh dấu nhiệm kỳ thứ 2 của Khoa Công nghệ thông tin, Khoa được giao đào tạo thêm các ngành mới và thành lập thêm các đơn vị trực thuộc để đảm bả ...

### web_003 - web_search

**Câu hỏi:** ICTU có lịch tuyển sinh mới nhất không?

**Kết quả:** Đạt

- Expected tool: `any`
- Predicted tool: `fallback_rag`
- Expected flow: `web_search`
- Predicted flow: `web_search` / `web_first`
- Retrieval mode: `web_search`
- Chunks used: `4`
- Sources: https://fet.ictu.edu.vn/tuyen-sinh-thac-si-nam-2026-co-hoi-hoc-truoc-danh-cho-sinh-vien-ictu/, http://laptrinh.ictu.edu.vn/, https://ictu.edu.vn/ictu-gianh-giai-ba-cuoc-thi-innovation-tech-challenge-2025-do-samsung-to-chuc/

**Trích ngữ cảnh truy xuất:**

[Web search ICTU | title: Tuyểnsinhthạc sĩ năm 2026 –cơhội học trước dành... | source: https://fet.ictu.edu.vn/tuyen-sinh-thac-si-nam-2026-co-hoi-hoc-truoc-danh-cho-sinh-vien-ictu/] 12/03/2026 TUYỂN SINH THẠC SĨ NĂM 2026 – CƠ HỘI HỌC TRƯỚC DÀNH CHO SINH VIÊN ICTU Khoa Kỹ thuật và Công nghệ, Trường Đại học Công nghệ Thông tin và Truyền thông – Đại học Thái Nguyên (ICTU) chính thức thông báo tuyển sinh đào tạo trình độ ...

### web_004 - web_search

**Câu hỏi:** ICTU có tin tức mới nhất về học phí không?

**Kết quả:** Đạt

- Expected tool: `any`
- Predicted tool: `school_policy_rag`
- Expected flow: `web_search`
- Predicted flow: `web_search` / `web_first`
- Retrieval mode: `web_search`
- Chunks used: `4`
- Sources: https://ictu.edu.vn/tai-sao-an-toan-thong-tin-tro-nen-quan-trong-hon-bao-gio-het-trong-thap-ky-toi/, https://ictu.edu.vn/ictu-vtieducation/, https://ictu.edu.vn/he-thong-phan-mem-chup-anh-ao-buoc-tien-moi-trong-dao-tao-ky-thuat-nhiep-anh/

**Trích ngữ cảnh truy xuất:**

[Web search ICTU | title: Tại sao an toàn thôngtintrở nên quan trọng hơn bao giờ hết trong... | source: https://ictu.edu.vn/tai-sao-an-toan-thong-tin-tro-nen-quan-trong-hon-bao-gio-het-trong-thap-ky-toi/] Tại sao an toàn thông tin trở nên quan trọng hơn bao giờ hết trong thập kỷ tới? Theo báo cáo của Cybersecurity Ventures, tạp chí nghiên cứu hàng đầu thế giới về nền kinh tế mạng toàn cầu cho thấy tổng tổn thất do tộ ...

### web_005 - web_search

**Câu hỏi:** ICTU có thông báo mới về bảo hiểm y tế sinh viên không?

**Kết quả:** Đạt

- Expected tool: `any`
- Predicted tool: `school_policy_rag`
- Expected flow: `web_search`
- Predicted flow: `web_search` / `web_first`
- Retrieval mode: `web_search`
- Chunks used: `4`
- Sources: https://en.ictu.edu.vn/, https://ictu.edu.vn/ictu-to-chuc-tuyen-dung-ung-vien-cho-cong-ty-tnhh-lens-viet-nam/, https://fet.ictu.edu.vn/tuyen-sinh-thac-si-nam-2026-co-hoi-hoc-truoc-danh-cho-sinh-vien-ictu/

**Trích ngữ cảnh truy xuất:**

[Web search ICTU | title: ICTU– University of Information and Communication Technology | source: https://en.ictu.edu.vn/] On March 4, 2026, Thai Nguyen University of Information and Communication Technology (ICTU) welcomed and held a working session with a high-level delegation from Kyungpook National University (KNU), Republic of Korea. [Web search ICTU | title: ICTUtổ chức tuyển dụng ứngviêncho Công ty TNHH Lens vi ...

### web_006 - web_search

**Câu hỏi:** ICTU cập nhật lịch học mới nhất ở đâu?

**Kết quả:** Đạt

- Expected tool: `any`
- Predicted tool: `student_faq_rag`
- Expected flow: `web_search`
- Predicted flow: `web_search` / `web_first`
- Retrieval mode: `web_search`
- Chunks used: `4`
- Sources: https://fet.ictu.edu.vn/doi-ngu-cbgv-cua-fet-ictu-tiep-tuc-tham-du-chuong-trinh-hoi-thao-chuong-trinh-dao-tao-cho-nganh-cong-nghiep-vi-mach-ban-dan-den-nam-2030-thach-thuc-va-giai-phap/, https://ictu.edu.vn/tan-sinh-vien-khoa-17-phan-khoi-trong-ngay-dau-nhap-hoc/, http://ect.ictu.edu.vn/

**Trích ngữ cảnh truy xuất:**

[Web search ICTU | title: Đội ngũ CBGV của FET -ICTUtiếp tục tham dự Chương trình Hội thảo... | source: https://fet.ictu.edu.vn/doi-ngu-cbgv-cua-fet-ictu-tiep-tuc-tham-du-chuong-trinh-hoi-thao-chuong-trinh-dao-tao-cho-nganh-cong-nghiep-vi-mach-ban-dan-den-nam-2030-thach-thuc-va-giai-phap/] 16/05/2024 Đội ngũ CBGV của FET – ICTU tiếp tục tham dự Chương trình Hội thảo “Chương trình đào tạo cho ngành Công nghiệp Vi mạch ...

### web_007 - web_search

**Câu hỏi:** ICTU cập nhật lịch thi mới nhất cho sinh viên ở đâu?

**Kết quả:** Đạt

- Expected tool: `any`
- Predicted tool: `student_faq_rag`
- Expected flow: `web_search`
- Predicted flow: `web_search` / `web_first`
- Retrieval mode: `web_search`
- Chunks used: `1`
- Sources: https://en.ictu.edu.vn/

**Trích ngữ cảnh truy xuất:**

[Web search ICTU | title: ICTU– University of Information and Communication Technology | source: https://en.ictu.edu.vn/] On March 4, 2026, Thai Nguyen University of Information and Communication Technology (ICTU) welcomed and held a working session with a high-level delegation from Kyungpook National University (KNU), Republic of Korea.

### web_008 - web_search

**Câu hỏi:** ICTU gần đây có thông báo xét tốt nghiệp nào?

**Kết quả:** Đạt

- Expected tool: `any`
- Predicted tool: `student_faq_rag`
- Expected flow: `web_search`
- Predicted flow: `web_search` / `web_first`
- Retrieval mode: `web_search`
- Chunks used: `4`
- Sources: https://fet.ictu.edu.vn/thong-bao-355-tb-dhcntttt-nguong-diem-xet-tuyen-theo-diem-thi-tot-nghiep-thpt-vao-cac-nganh-dao-tao-he-dhcq-nam-2021/, https://ictu.edu.vn/thong-bao-423-v-v-cong-bo-diem-trung-tuyen-he-dai-hoc-chinh-quy-theo-phuong-thuc-xet-tuyen-theo-ket-qua-thi-tot-nghiep-thpt-nam-2021/, https://fet.ictu.edu.vn/

**Trích ngữ cảnh truy xuất:**

[Web search ICTU | title: Thôngbáo355/TB-ĐHCNTT&TT ngưỡng điểmxéttuyển theo điểm thi... | source: https://fet.ictu.edu.vn/thong-bao-355-tb-dhcntttt-nguong-diem-xet-tuyen-theo-diem-thi-tot-nghiep-thpt-vao-cac-nganh-dao-tao-he-dhcq-nam-2021/] Thông báo 355/TB-ĐHCNTT&TT ngưỡng điểm xét tuyển theo điểm thi tốt nghiệp THPT vào các ngành đào tạo hệ ĐHCQ năm 2021 Căn cứ Kết luận cuộc họp của Hội đồng tuyển sinh Trường Đại h ...

### web_009 - web_search

**Câu hỏi:** ICTU có tin mới về việc làm hoặc tuyển dụng sinh viên không?

**Kết quả:** Đạt

- Expected tool: `any`
- Predicted tool: `student_faq_rag`
- Expected flow: `web_search`
- Predicted flow: `web_search` / `web_first`
- Retrieval mode: `web_search`
- Chunks used: `4`
- Sources: https://ictu.edu.vn/200-sinh-vien-ictu-phong-van-tuyen-dung-truc-tiep-truoc-them-tot-nghiep/, https://fet.ictu.edu.vn/co-hoi-vang-den-duc-lam-viec-thuc-tap-tai-siemens-porsche-bosch-cho-sinh-vien-co-dien-tu-cong-nghe-o-to-va-tu-dong-hoa-ictu/, https://mmc.ictu.edu.vn/cong-ty-water-media-wevic-ve-ictu-tuyen-dung-co-hoi-ung-tuyen-cho-sinh-vien-nam-cuoi-ac

**Trích ngữ cảnh truy xuất:**

[Web search ICTU | title: 200sinhviênICTUphỏng vấntuyểndụngtrực tiếp trước... -ICTU | source: https://ictu.edu.vn/200-sinh-vien-ictu-phong-van-tuyen-dung-truc-tiep-truoc-them-tot-nghiep/] 200 sinh viên ICTU phỏng vấn tuyển dụng trực tiếp trước thềm tốt nghiệp Sáng ngày 18/4/2025, Trường Đại học Công nghệ Thông tin và Truyền thông (ICTU) – Đại học Thái Nguyên đã phối hợp cùng Tập đoàn Foxconn tổ chức buổi tuyển dụng t ...

### web_010 - web_search

**Câu hỏi:** ICTU năm nay có thông báo học bổng mới nhất không?

**Kết quả:** Đạt

- Expected tool: `any`
- Predicted tool: `school_policy_rag`
- Expected flow: `web_search`
- Predicted flow: `web_search` / `web_first`
- Retrieval mode: `web_search`
- Chunks used: `4`
- Sources: http://ect.ictu.edu.vn/, http://laptrinh.ictu.edu.vn/, https://ictu.edu.vn/ictu-to-chuc-ky-niem-39-nam-ngay-nha-giao-viet-nam/

**Trích ngữ cảnh truy xuất:**

[Web search ICTU | title: Khoa Công nghệ Điện tử và Truyềnthông- ĐạihọcCông nghệ... | source: http://ect.ictu.edu.vn/] Ứng dụng khoa học công nghệ Sau một thời gian tích cực nghiên cứu, thiết kế và thi công nhóm Giảng viên Bộ môn Công nghệ Kỹ thuật máy tính đã hoàn thành hệ thống các bài thực ... Hoạt động sinh viên Nhằm tiếp tục nâng cao tính thực tiễn của hoạt động đào tạo ngành Kỹ thuật Y sinh tại Khoa Công nghệ Đ ...

### web_011 - web_search

**Câu hỏi:** ICTU có cập nhật mới nhất về email sinh viên không?

**Kết quả:** Đạt

- Expected tool: `any`
- Predicted tool: `student_faq_rag`
- Expected flow: `web_search`
- Predicted flow: `web_search` / `web_first`
- Retrieval mode: `web_search`
- Chunks used: `4`
- Sources: http://laptrinh.ictu.edu.vn/, https://ictu.edu.vn/tan-sinh-vien-khoa-17-phan-khoi-trong-ngay-dau-nhap-hoc/, https://mmc.ictu.edu.vn/hoc-3d-thuc-chien-cung-doanh-nghiep-tai-ictu-co-hoi-vang-danh-cho-sinh-vien-ac

**Trích ngữ cảnh truy xuất:**

[Web search ICTU | title: Home -ICTU: Online Judge | source: http://laptrinh.ictu.edu.vn/] SinhviênICTUCóđam mê lập trình, yêu thích thuật toán và tư duy logicƯu tiênsinhviêncótinh thần tự học, chủ động và nghiêm túc trong học tập. [Web search ICTU | title: Tânsinhviênkhóa 17 phấn khởi trong ngày đầu nhập học – [ICTU] | source: https://ictu.edu.vn/tan-sinh-vien-khoa-17-phan-khoi-trong-ngay-dau-nhap-hoc/] Tân sinh viê ...

### web_012 - web_search

**Câu hỏi:** ICTU có thông báo mới về nhập học cho tân sinh viên không?

**Kết quả:** Đạt

- Expected tool: `any`
- Predicted tool: `student_handbook_rag`
- Expected flow: `web_search`
- Predicted flow: `web_search` / `web_first`
- Retrieval mode: `web_search`
- Chunks used: `4`
- Sources: https://ictu.edu.vn/tan-sinh-vien-khoa-17-phan-khoi-trong-ngay-dau-nhap-hoc/, https://mmc.ictu.edu.vn/tan-sinh-vien-khoa-17-phan-khoi-trong-ngay-dau-nhap-hoc, https://fet.ictu.edu.vn/tuyen-sinh-thac-si-nam-2026-co-hoi-hoc-truoc-danh-cho-sinh-vien-ictu/

**Trích ngữ cảnh truy xuất:**

[Web search ICTU | title: Tânsinhviênkhóa 17 phấn khởi trong ngày đầunhậphọc– [ICTU] | source: https://ictu.edu.vn/tan-sinh-vien-khoa-17-phan-khoi-trong-ngay-dau-nhap-hoc/] Tân sinh viên khóa 17 phấn khởi trong ngày đầu nhập học Không biết tự bao giờ mùa thu được các thế hệ sinh viên gọi một cách thân thương là “mùa nhập học”. Đến hẹn lại lên, mùa nhập học năm nay của Trường Đại học Công nghệ Thông tin và Truyền thôn ...

### web_013 - web_search

**Câu hỏi:** ICTU có tin tức mới nhất về cổng thông tin sinh viên không?

**Kết quả:** Đạt

- Expected tool: `any`
- Predicted tool: `fallback_rag`
- Expected flow: `web_search`
- Predicted flow: `web_search` / `web_first`
- Retrieval mode: `web_search`
- Chunks used: `4`
- Sources: https://ictu.edu.vn/category/tin-tuc/page/14/, https://ictu.edu.vn/category/tin-tuc/page/22/, https://ictu.edu.vn/tai-sao-an-toan-thong-tin-tro-nen-quan-trong-hon-bao-gio-het-trong-thap-ky-toi/

**Trích ngữ cảnh truy xuất:**

[Web search ICTU | title: Tintức- Sự kiện -ICTU | source: https://ictu.edu.vn/category/tin-tuc/page/14/] 12/08/2024 Tối ngày 10/8, tại Nhà hát Ca, Múa, Nhạc dân gian Việt Bắc (TP Thái Nguyên), đội văn nghệ Công đoàn Trường Đại học Công nghệ Thông tin và Truyền thông (ICTU) đã tham gia Hội diễn văn nghệ công nhân, viên chức, lao động... [Web search ICTU | title: Tintức- Sự kiện -ICTU | source: https://ictu.edu.vn/cate ...

### web_014 - web_search

**Câu hỏi:** ICTU có thông báo mới nhất về ký túc xá không?

**Kết quả:** Đạt

- Expected tool: `any`
- Predicted tool: `fallback_rag`
- Expected flow: `web_search`
- Predicted flow: `web_search` / `web_first`
- Retrieval mode: `web_search`
- Chunks used: `4`
- Sources: http://laptrinh.ictu.edu.vn/, https://ictu.edu.vn/ictu-ron-rang-don-tan-sinh-vien-lam-thu-tuc-nhap-hoc/, https://ictu.edu.vn/ictu-vtieducation/

**Trích ngữ cảnh truy xuất:**

[Web search ICTU | title: Home -ICTU: Online Judge | source: http://laptrinh.ictu.edu.vn/] THÔNGBÁOĐĂNGKÝTHAM GIA CUỘC THI LẬP TRÌNHICTUOJ CHALLENGE 2025 Code mạnh – Tư duy nhanh – Khẳng định đẳng cấp sinh viênICTU! GIỚI THIỆU CUỘC THI. [Web search ICTU | title: ICTUrộn ràng đón tân sinh viên làm thủtụcnhập học -ICTU | source: https://ictu.edu.vn/ictu-ron-rang-don-tan-sinh-vien-lam-thu-tuc-nhap-hoc/] ICTU rộn ràng đó ...

### web_015 - web_search

**Câu hỏi:** ICTU có lịch sự kiện sinh viên mới nhất hôm nay không?

**Kết quả:** Đạt

- Expected tool: `any`
- Predicted tool: `fallback_rag`
- Expected flow: `web_search`
- Predicted flow: `web_search` / `web_first`
- Retrieval mode: `web_search`
- Chunks used: `1`
- Sources: https://en.ictu.edu.vn/

**Trích ngữ cảnh truy xuất:**

[Web search ICTU | title: ICTU– University of Information and Communication Technology | source: https://en.ictu.edu.vn/] On March 4, 2026, Thai Nguyen University of Information and Communication Technology (ICTU) welcomed and held a working session with a high-level delegation from Kyungpook National University (KNU), Republic of Korea.
