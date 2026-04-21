# Project Tools

Các file trong `tools/` là tiện ích vận hành, không nằm trong runtime chính của FastAPI app.

- `data_pipeline/`: chuyển PDF/Markdown, sinh QA, sửa dấu tiếng Việt, import corpus.
- `evaluation/`: benchmark router/retrieval và phân tích dataset.
- `reporting/`: sinh báo cáo, sơ đồ, slide và tài liệu bàn giao.
- `manual/`: công cụ test thủ công khi cần debug local.

Chạy từ thư mục gốc project, ví dụ:

```powershell
.\venv\Scripts\python.exe tools\evaluation\evaluate_chatbot.py
```
