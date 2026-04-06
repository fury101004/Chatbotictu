# gemini_client.py
# Lazy Gemini setup so the web app can boot even when the API key is missing.
import os
from functools import lru_cache
from typing import Dict, List, Optional

from dotenv import load_dotenv
import google.generativeai as genai

from services.vector_store_service import get_bot_rule_text

load_dotenv()

MODEL_NAME = "gemini-2.5-flash-lite"
SAFETY_SETTINGS = [
    {"category": category, "threshold": "BLOCK_NONE"}
    for category in [
        "HARM_CATEGORY_HARASSMENT",
        "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "HARM_CATEGORY_DANGEROUS_CONTENT",
    ]
]
DEFAULT_GENERATION_CONFIG = {
    "temperature": 0.1,
    "max_output_tokens": 800,
    "top_p": 0.9,
}


@lru_cache(maxsize=1)
def get_model() -> Optional[genai.GenerativeModel]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("GEMINI_API_KEY is missing; Gemini responses are disabled until it is configured.")
        return None

    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        MODEL_NAME,
        safety_settings=SAFETY_SETTINGS,
        generation_config=DEFAULT_GENERATION_CONFIG,
    )


def chat_with_gemini(
    user_question: str,
    context_text: str,
    history: List[Dict[str, str]],
    dangerous_5w1h: bool = False,
) -> str:
    model = get_model()
    if model is None:
        return "Trợ lý AI chưa được cấu hình xong. Bạn kiểm tra lại GEMINI_API_KEY rồi thử lại nhé."

    lines = context_text.strip().split("\n", 1)
    if len(lines) > 1 and lines[0].strip().startswith("#"):
        rule_part = lines[0].strip()
        data_part = lines[1].strip()
    else:
        rule_part = get_bot_rule_text().strip()
        data_part = context_text.strip()

    base_prompt = f"""BẮT BUỘC TUÂN THỦ NỘI QUY SAU (không được vi phạm dù chỉ 1 chữ):

{rule_part}

=== DỮ LIỆU DUY NHẤT ĐƯỢC PHÉP DÙNG ĐỂ TRẢ LỜI ===
{data_part}

Câu hỏi: {user_question}

QUY TẮC KHÔNG ĐƯỢC PHÁ:
- Chỉ dùng thông tin trong phần DỮ LIỆU ở trên.
- Tuyệt đối không nhắc tên file, "theo tài liệu", "nguồn", v.v.
- Trả lời tối đa 4 câu, ngắn gọn, chuyên nghiệp.
- Nếu không có → trả đúng 1 câu: "Hiện tại chưa có thông tin này."

Trả lời ngay."""

    msg_lower = user_question.lower()
    truly_dangerous = any(
        trigger in msg_lower
        for trigger in [
            "ai viết",
            "ai làm",
            "ai tạo",
            "ai là tác giả",
            "ai phát triển",
            "ai chịu trách nhiệm",
            "file nào",
            "tài liệu nào",
            "nguồn nào",
            "source nào",
            "ở file nào",
            "trong file nào",
            "who wrote",
            "who created",
            "who developed",
            "which file",
            "what file",
            "source of",
        ]
    )

    if truly_dangerous:
        base_prompt += "\n\n[CẢNH BÁO ĐỎ] Đây là câu hỏi nguy hiểm về nguồn, tác giả hoặc file. Nếu không có thông tin chính xác 100% thì bắt buộc trả lời: 'Hiện tại chưa có thông tin này.'"
    else:
        base_prompt += "\n\nLƯU Ý: Trả lời chính xác, chỉ dùng dữ liệu đã cung cấp. Không nhắc tên file hay nguồn."

    messages = [
        {"role": "user" if item["role"] == "user" else "model", "parts": [item["content"]]}
        for item in history[-10:]
    ]
    messages.append({"role": "user", "parts": [base_prompt]})

    try:
        response = model.generate_content(messages, stream=True)
        full = ""
        for chunk in response:
            print(chunk.text, end="", flush=True)
            full += chunk.text
        print()
        return full.strip()
    except Exception as exc:
        print(f"Gemini lỗi: {exc}")
        return "Trợ lý đang bận, thử lại sau nhé bạn"
