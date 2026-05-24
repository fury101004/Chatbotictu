# Báo cáo kiểm thử 30 câu hỏi ICTU

- Thời gian chạy: 2026-05-20T18:03:19+07:00
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
- Độ trễ trung bình: 130.95 ms
- Số chunk trung bình: 2.1
- Web search configured: True
- Live web enabled: False
- Use LLM router: False
- Embedding backend ready: True

## Kết quả từng câu

| id | nhóm | route | flow | source | pass | latency ms | nguồn đầu tiên |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| local_001 | local_data | yes | yes | yes | yes | 1902.45 | student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md |
| local_002 | local_data | yes | yes | yes | yes | 127.97 | student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md |
| local_003 | local_data | yes | yes | yes | yes | 125.91 | student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md |
| local_004 | local_data | yes | yes | yes | yes | 127.89 | student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md |
| local_005 | local_data | yes | yes | yes | yes | 126.96 | student_handbooks/8. SO TAY SINH VIEN 2025-2026.questions.md |
| local_006 | local_data | yes | yes | yes | yes | 134.06 | student_handbooks/6. SO TAY SINH VIEN 2023-2024.questions.md |
| local_007 | local_data | yes | yes | yes | yes | 129.02 | student_handbooks/6. SO TAY SINH VIEN 2023-2024.questions.md |
| local_008 | local_data | yes | yes | yes | yes | 145.45 | student_handbooks/1. SO TAY SINH VIEN 2018-2019.questions.md |
| local_009 | local_data | yes | yes | yes | yes | 144.26 | student_handbooks/6. SO TAY SINH VIEN 2023-2024.questions.md |
| local_010 | local_data | yes | yes | yes | yes | 138.04 | student_handbooks/6. SO TAY SINH VIEN 2023-2024.questions.md |
| local_011 | local_data | yes | yes | yes | yes | 135.0 | student_handbooks/1. SO TAY SINH VIEN 2018-2019.questions.md |
| local_012 | local_data | yes | yes | yes | yes | 139.24 | student_handbooks/1. SO TAY SINH VIEN 2018-2019.questions.md |
| local_013 | local_data | yes | yes | yes | yes | 146.31 | student_handbooks/1. SO TAY SINH VIEN 2018-2019.questions.md |
| local_014 | local_data | yes | yes | yes | yes | 145.46 | student_handbooks/1. SO TAY SINH VIEN 2018-2019.questions.md |
| local_015 | local_data | yes | yes | no | no | 258.26 | uploads/student_faq_rag/_knowledge_base_chat/approved-chat-78-khoa-24-nay-can-bao-nhieu-tin-chi-de-tot-nghiep-.md |
| web_001 | web_search | yes | yes | - | yes | 0.2 | - |
| web_002 | web_search | yes | yes | - | yes | 0.15 | - |
| web_003 | web_search | yes | yes | - | yes | 0.14 | - |
| web_004 | web_search | yes | yes | - | yes | 0.14 | - |
| web_005 | web_search | yes | yes | - | yes | 0.15 | - |
| web_006 | web_search | yes | yes | - | yes | 0.14 | - |
| web_007 | web_search | yes | yes | - | yes | 0.14 | - |
| web_008 | web_search | yes | yes | - | yes | 0.14 | - |
| web_009 | web_search | yes | yes | - | yes | 0.14 | - |
| web_010 | web_search | yes | yes | - | yes | 0.14 | - |
| web_011 | web_search | yes | yes | - | yes | 0.15 | - |
| web_012 | web_search | yes | yes | - | yes | 0.14 | - |
| web_013 | web_search | yes | yes | - | yes | 0.14 | - |
| web_014 | web_search | yes | yes | - | yes | 0.13 | - |
| web_015 | web_search | yes | yes | - | yes | 0.13 | - |

## Ca cần xem lại
- local_015: predicted_tool=student_faq_rag, flow=local_data/local_first, source_hit=False
