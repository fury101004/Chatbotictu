# Báo cáo kiểm thử 30 câu hỏi ICTU

- Thời gian chạy: 2026-05-20T18:11:27+07:00
- Tổng số câu: 30
- Nhóm dữ liệu nội bộ: 15
- Nhóm luồng web search: 15
- Overall accuracy: 96.67%
- Local accuracy: 93.33%
- Web-flow accuracy: 100.00%
- Route accuracy: 100.00%
- Flow accuracy: 100.00%
- Source hit rate: 93.33%
- Source top-1 hit rate: 93.33%
- Độ trễ trung bình: 6602.89 ms
- Số chunk trung bình: 3.9
- Web search configured: True
- Live web enabled: True
- Use LLM router: False
- Embedding backend ready: True

## Kết quả từng câu

| id | nhóm | route | flow | source | pass | latency ms | nguồn đầu tiên |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| local_001 | local_data | yes | yes | yes | yes | 1590.38 | student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md |
| local_002 | local_data | yes | yes | yes | yes | 138.28 | student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md |
| local_003 | local_data | yes | yes | yes | yes | 142.42 | student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md |
| local_004 | local_data | yes | yes | yes | yes | 145.77 | student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md |
| local_005 | local_data | yes | yes | yes | yes | 148.89 | student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md |
| local_006 | local_data | yes | yes | yes | yes | 143.82 | student_handbooks/6. SO TAY SINH VIEN 2023-2024.questions.md |
| local_007 | local_data | yes | yes | yes | yes | 141.9 | student_handbooks/6. SO TAY SINH VIEN 2023-2024.questions.md |
| local_008 | local_data | yes | yes | yes | yes | 154.08 | student_handbooks/1. SO TAY SINH VIEN 2018-2019.questions.md |
| local_009 | local_data | yes | yes | yes | yes | 154.79 | student_handbooks/6. SO TAY SINH VIEN 2023-2024.questions.md |
| local_010 | local_data | yes | yes | yes | yes | 152.53 | student_handbooks/6. SO TAY SINH VIEN 2023-2024.questions.md |
| local_011 | local_data | yes | yes | yes | yes | 146.24 | student_handbooks/1. SO TAY SINH VIEN 2018-2019.questions.md |
| local_012 | local_data | yes | yes | yes | yes | 155.0 | student_handbooks/1. SO TAY SINH VIEN 2018-2019.questions.md |
| local_013 | local_data | yes | yes | yes | yes | 162.9 | student_handbooks/1. SO TAY SINH VIEN 2018-2019.questions.md |
| local_014 | local_data | yes | yes | yes | yes | 179.07 | student_handbooks/1. SO TAY SINH VIEN 2018-2019.questions.md |
| local_015 | local_data | yes | yes | no | no | 119.65 | uploads/student_faq_rag/_knowledge_base_chat/approved-chat-78-khoa-24-nay-can-bao-nhieu-tin-chi-de-tot-nghiep-.md |
| web_001 | web_search | yes | yes | - | yes | 12044.16 | https://fet.ictu.edu.vn/category/thong-bao/thong-bao-sinh-vien/ |
| web_002 | web_search | yes | yes | - | yes | 10282.87 | https://ictu.edu.vn/ |
| web_003 | web_search | yes | yes | - | yes | 26407.88 | https://fet.ictu.edu.vn/tuyen-sinh-thac-si-nam-2026-co-hoi-hoc-truoc-danh-cho-sinh-vien-ictu/ |
| web_004 | web_search | yes | yes | - | yes | 4999.87 | https://ictu.edu.vn/tai-sao-an-toan-thong-tin-tro-nen-quan-trong-hon-bao-gio-het-trong-thap-ky-toi/ |
| web_005 | web_search | yes | yes | - | yes | 4994.23 | https://en.ictu.edu.vn/ |
| web_006 | web_search | yes | yes | - | yes | 5374.68 | https://fet.ictu.edu.vn/doi-ngu-cbgv-cua-fet-ictu-tiep-tuc-tham-du-chuong-trinh-hoi-thao-chuong-trinh-dao-tao-cho-nganh-cong-nghiep-vi-mach-ban-dan-den-nam-2030-thach-thuc-va-giai-phap/ |
| web_007 | web_search | yes | yes | - | yes | 10459.05 | https://en.ictu.edu.vn/ |
| web_008 | web_search | yes | yes | - | yes | 11822.74 | https://fet.ictu.edu.vn/thong-bao-355-tb-dhcntttt-nguong-diem-xet-tuyen-theo-diem-thi-tot-nghiep-thpt-vao-cac-nganh-dao-tao-he-dhcq-nam-2021/ |
| web_009 | web_search | yes | yes | - | yes | 10448.11 | https://ictu.edu.vn/200-sinh-vien-ictu-phong-van-tuyen-dung-truc-tiep-truoc-them-tot-nghiep/ |
| web_010 | web_search | yes | yes | - | yes | 22304.12 | http://ect.ictu.edu.vn/ |
| web_011 | web_search | yes | yes | - | yes | 24541.49 | http://laptrinh.ictu.edu.vn/ |
| web_012 | web_search | yes | yes | - | yes | 4955.21 | https://ictu.edu.vn/tan-sinh-vien-khoa-17-phan-khoi-trong-ngay-dau-nhap-hoc/ |
| web_013 | web_search | yes | yes | - | yes | 9398.91 | https://ictu.edu.vn/category/tin-tuc/page/14/ |
| web_014 | web_search | yes | yes | - | yes | 25435.28 | http://laptrinh.ictu.edu.vn/ |
| web_015 | web_search | yes | yes | - | yes | 10942.46 | https://en.ictu.edu.vn/ |

## Ca cần xem lại
- local_015: predicted_tool=student_faq_rag, flow=local_data/local_first, source_hit=False
