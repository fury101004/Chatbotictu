import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from providers.gemini_provider import GeminiProvider
from shared.prompt_loader import render_prompt
from services.vector_store_service import get_bot_rule_text

load_dotenv()

PRIMARY_MODEL_NAME = GeminiProvider.primary_model_name
FALLBACK_MODEL_NAME = GeminiProvider.fallback_model_name
MODEL_NAME = PRIMARY_MODEL_NAME
SAFETY_SETTINGS = GeminiProvider.safety_settings
DEFAULT_GENERATION_CONFIG = GeminiProvider.default_generation_config


def get_model(model_name: str = PRIMARY_MODEL_NAME) -> Optional[Any]:
    return GeminiProvider.get_model(model_name)


def _looks_like_quota_error(exc: Exception) -> bool:
    return GeminiProvider.looks_like_quota_error(exc)


def generate_content_with_fallback(
    contents: Any,
    *,
    generation_config: Optional[dict] = None,
    safety_settings: Optional[list[dict]] = None,
    request_options: Optional[dict] = None,
    stream: bool = False,
    preferred_model: str = PRIMARY_MODEL_NAME,
) -> tuple[Any, str]:
    model = get_model(preferred_model)
    if model is None:
        raise RuntimeError("Gemini model is not configured.")

    try:
        response = model.generate_content(
            contents,
            generation_config=generation_config,
            safety_settings=safety_settings,
            request_options=request_options,
            stream=stream,
        )
        return response, preferred_model
    except Exception as exc:
        if preferred_model != PRIMARY_MODEL_NAME or not _looks_like_quota_error(exc):
            raise

        fallback_model = get_model(FALLBACK_MODEL_NAME)
        if fallback_model is None:
            raise

        print(
            f"Gemini {PRIMARY_MODEL_NAME} quota/free-tier limit detected; retrying with "
            f"{FALLBACK_MODEL_NAME}. Original error: {exc}"
        )
        response = fallback_model.generate_content(
            contents,
            generation_config=generation_config,
            safety_settings=safety_settings,
            request_options=request_options,
            stream=stream,
        )
        return response, FALLBACK_MODEL_NAME


def _build_gemini_prompt(rule_part: str, data_part: str, user_question: str, *, dangerous: bool) -> str:
    if dangerous:
        danger_notice = (
            "\n- [CẢNH BÁO ĐỎ] Đây là câu hỏi nguy hiểm về nguồn, tác giả hoặc file. "
            "Nếu không có thông tin chính xác 100% thì bắt buộc trả lời: "
            '"Hiện tại chưa có thông tin này."'
        )
    else:
        danger_notice = "\n- Trả lời chính xác, chỉ dùng dữ liệu đã cung cấp. Không nhắc tên file hay nguồn."

    return render_prompt(
        "gemini_answer.md",
        rule_part=rule_part,
        data_part=data_part,
        user_question=user_question,
        danger_notice=danger_notice,
    )


def chat_with_gemini(
    user_question: str,
    context_text: str,
    history: List[Dict[str, str]],
    dangerous_5w1h: bool = False,
) -> str:
    del dangerous_5w1h
    if get_model() is None:
        return "Trợ lý AI chưa được cấu hình xong. Bạn kiểm tra lại GEMINI_API_KEY rồi thử lại nhé."

    lines = context_text.strip().split("\n", 1)
    if len(lines) > 1 and lines[0].strip().startswith("#"):
        rule_part = lines[0].strip()
        data_part = lines[1].strip()
    else:
        rule_part = get_bot_rule_text().strip()
        data_part = context_text.strip()

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

    base_prompt = _build_gemini_prompt(
        rule_part,
        data_part,
        user_question,
        dangerous=truly_dangerous,
    )

    messages = [
        {"role": "user" if item["role"] == "user" else "model", "parts": [item["content"]]}
        for item in history[-10:]
    ]
    messages.append({"role": "user", "parts": [base_prompt]})

    try:
        response, used_model = generate_content_with_fallback(messages, stream=True)
        if used_model != PRIMARY_MODEL_NAME:
            print(f"chat_with_gemini switched to fallback model: {used_model}")
        full = ""
        for chunk in response:
            print(chunk.text, end="", flush=True)
            full += chunk.text
        print()
        return full.strip()
    except Exception as exc:
        print(f"Gemini lỗi: {exc}")
        return "Trợ lý đang bận, thử lại sau nhé bạn"
