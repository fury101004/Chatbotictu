from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.web.context import page_context
from app.web.templates import templates


router = APIRouter(tags=["pages"])


@router.get("/")
def home(request: Request):
    highlights = [
        {
            "kicker": "Chat theo mục tiêu",
            "title": "3 agent tra cứu theo route",
            "copy": "Hỏi đáp được route sang handbook, policy hoặc faq để câu trả lời bám đúng ngữ cảnh hơn.",
        },
        {
            "kicker": "Upload và đồng bộ",
            "title": "Nạp tài liệu và rebuild ngay trên web",
            "copy": "Tài liệu PDF, DOCX hoặc Markdown có thể được đưa vào pipeline RAG mà không cần chạy lệnh thủ công.",
        },
        {
            "kicker": "Cấu hình mô hình",
            "title": "Ollama và Gemini cùng song song",
            "copy": "Chuyển provider bằng `.env`, giữ nguyên giao diện vận hành và luồng RAG hiện có.",
        },
    ]
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context=page_context(request, active="home", title="Home", highlights=highlights),
    )


@router.get("/chat")
def chat_ui(request: Request):
    suggestions = [
        "Bảo hiểm y tế học kỳ này đóng khi nào?",
        "Sổ tay sinh viên có hướng dẫn hủy học phần không?",
        "Quyết định học bổng mới nhất áp dụng cho năm nào?",
    ]
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context=page_context(request, active="chat", title="Chat", suggestions=suggestions),
    )


@router.get("/upload")
def upload(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="upload.html",
        context=page_context(request, active="upload", title="Upload"),
    )


@router.get("/vector")
def vector(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="vector.html",
        context=page_context(request, active="vector", title="Vector"),
    )


@router.get("/config")
def config_view(request: Request):
    config_groups = [
        {
            "title": "LLM",
            "entries": [
                ("LLM_PROVIDER", "Chọn `ollama`, `gemini` hoặc `auto`."),
                ("OLLAMA_URL", "Địa chỉ backend Ollama local."),
                ("OLLAMA_MODEL", "Model mặc định khi dùng Ollama."),
                ("GEMINI_API_KEY", "API key cho Gemini."),
                ("GEMINI_MODEL", "Model mặc định khi dùng Gemini."),
            ],
        },
        {
            "title": "Data và Upload",
            "entries": [
                ("RAW_DATA_DIR", "Thư mục file nguồn PDF/DOCX/Markdown."),
                ("UPLOADS_DIR_NAME", "Thư mục con chứa file upload từ web."),
                ("CLEAN_MD_DIR", "Markdown đã làm sạch."),
                ("RAG_MD_DIR", "Markdown tối ưu cho RAG."),
                ("VECTOR_DB_DIR", "Nơi lưu vector store route-based."),
                ("MAX_UPLOAD_SIZE_MB", "Giới hạn mỗi file upload."),
            ],
        },
        {
            "title": "Runtime",
            "entries": [
                ("CHAT_DB_NAME", "SQLite lưu lịch sử hội thoại."),
                ("SERVER_HOST", "Host khi chạy uvicorn."),
                ("SERVER_PORT", "Port của server."),
                ("UVICORN_RELOAD", "Bật tắt reload cho dev."),
            ],
        },
    ]
    return templates.TemplateResponse(
        request=request,
        name="config.html",
        context=page_context(request, active="config", title="Config", config_groups=config_groups),
    )


@router.get("/history")
def history_view(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context=page_context(request, active="history", title="History"),
    )


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    return RedirectResponse(url="/static/favicon.svg", status_code=307)
