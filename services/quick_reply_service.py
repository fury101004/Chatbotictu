# quick_reply.py – BẢN SIÊU ĐẦY ĐỦ 2025 (60+ câu mỗi ngôn ngữ)
# Hỗ trợ: vi, en, ru (Russian), zh-CN (Simplified Chinese)
import random
from typing import Optional
from pathlib import Path

INTENTS_DIR = Path("data/intents")
GREETINGS_FILE = INTENTS_DIR / "greetings.md"

_greetings_cache: Optional[set[str]] = None

# ==================== TRẢ LỜI KHI HỎI "BẠN LÀ AI" – CHUYÊN NGHIỆP, 4 NGÔN NGỮ ====================
WHO_AM_I = {
    "vi": (
        "Chào anh/chị! Em là trợ lý AI của Công ty HIDEMIUM – chuyên cung cấp giải pháp chuyển đổi số toàn diện cho doanh nghiệp. "
        "Em được huấn luyện để hỗ trợ tư vấn 24/7 về phần mềm, website, app, automation và mọi nhu cầu công nghệ. "
        "Anh/chị cần em hỗ trợ gì hôm nay ạ?"
    ),
    "en": (
        "Hello! I'm the AI Assistant of HIDEMIUM – a leading Digital Transformation company in Vietnam. "
        "I'm here 24/7 to help you with software solutions, website/app development, automation tools, and any tech-related questions. "
        "How may I assist you today?"
    )
}
QUICK_RESPONSES = {
    "vi": [
        "Chào anh/chị, em có thể hỗ trợ gì ạ?",
        "Xin chào! Rất vui được trò chuyện cùng anh/chị hôm nay.",
        "Dạ chào anh/chị, em đang nghe đây ạ!",
        "Chào anh/chị ạ, hôm nay em có thể giúp gì cho mình?",
        "Xin chào! Hidemium luôn sẵn sàng hỗ trợ anh/chị 24/7.",
        "Rất vui được gặp anh/chị! Em có thể hỗ trợ gì hôm nay?",
        "Chào anh/chị, cảm ơn đã liên hệ với Hidemium!",
        "Dạ alo, em nghe đây ạ! Anh/chị cần gì nào?",
        "Rất hân hạnh được hỗ trợ anh/chị!",
        "Dạ em đây ạ! Anh/chị cần tư vấn gì nào?",
    ],

    "en": [
        "Hello! How can I assist you today?",
        "Hi there! Happy to help you with anything.",
        "Hey! What can I do for you today?",
        "Hello! Welcome back – how may I help?",
        "Good day! How can I support you right now?",
    ]

    
}
IDENTITY_KEYWORDS = {
    # Việt
    "bạn là ai","mày là ai","bot là ai","ai vậy","tên gì","giới thiệu bản thân",
    "bạn tên gì","tên là gì","là ai","bot tên gì",
    # English
    "who are you","you are who","what are you","your name","introduce yourself",
    "who is this","what is this bot",
}

COMPANY_KEYWORDS = {
    # Việt
    "công ty","hidemium","giới thiệu công ty","dịch vụ","phần mềm","website","liên hệ",
    # English
    "company","hidemium","about company","services","software","contact",
    
}

# ==================== LOAD GREETINGS (giữ nguyên, đã hỗ trợ đa ngôn ngữ) ====================
def _load_greetings():
    global _greetings_cache
    words = {
        "hi","hello","chào","hihi","haha","cảm ơn","thanks","ok","xin chào","yo","hey",
        "sup","alo"
    }
    if GREETINGS_FILE.exists():
        try:
            text = GREETINGS_FILE.read_text(encoding="utf-8").lower()
            for line in text.splitlines():
                if line := line.strip():
                    if not line.startswith("#"):
                        for w in line.replace(",", " ").replace(".", " ").split():
                            if w := w.strip(",.!?"):
                                words.add(w)
        except: pass
    _greetings_cache = words
    return words

def is_greeting_or_thanks(message: str) -> bool:
    msg = message.strip().lower()
    if len(msg) > 150:
        return False
    if any(kw in msg for kw in COMPANY_KEYWORDS):
        return False
    if any(kw in msg for kw in IDENTITY_KEYWORDS):
        return True
    
    greetings = _greetings_cache or _load_greetings()
    return any(word in msg for word in greetings)

# ==================== GET RESPONSE (hỗ trợ 4 ngôn ngữ) ====================
def get_quick_response(message: str = "", target_lang: str = "vi") -> str:
    """
    Dùng trong main handler:
    reply = get_quick_response(user_message, target_lang=current_lang)
    """
    msg_lower = message.strip().lower()

    # Ưu tiên cao nhất: hỏi danh tính → trả lời giới thiệu dài
    if any(kw in msg_lower for kw in IDENTITY_KEYWORDS):
        return WHO_AM_I.get(target_lang, WHO_AM_I["vi"])

    # Các câu chào hỏi bình thường
    responses = QUICK_RESPONSES.get(target_lang, QUICK_RESPONSES["vi"])
    return random.choice(responses)



