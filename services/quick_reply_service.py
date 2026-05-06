from __future__ import annotations

import random
from pathlib import Path
from typing import Optional

from config.settings import settings


INTENTS_DIR = Path(settings.INTENTS_DIR)
GREETINGS_FILE = INTENTS_DIR / "greetings.md"
_greetings_cache: Optional[set[str]] = None

WHO_AM_I = {
    "vi": (
        "Em là trợ lý AI của ICTU, chuyên hỗ trợ tra cứu thông tin và giải đáp "
        "các câu hỏi liên quan đến nhà trường, học vụ và dịch vụ dành cho sinh viên."
    ),
    "en": (
        "I am ICTU's AI assistant, here to help with university information lookup "
        "and student support questions."
    ),
}

QUICK_RESPONSES = {
    "vi": [
        "Chào bạn, mình có thể hỗ trợ gì cho bạn hôm nay?",
        "Xin chào! Bạn cần mình tra cứu thông tin nào?",
        "Mình đang sẵn sàng hỗ trợ đây, bạn cứ hỏi nhé.",
    ],
    "en": [
        "Hello! How can I help you today?",
        "Hi there! What would you like to look up?",
        "I'm ready to help. Please go ahead with your question.",
    ],
}

IDENTITY_KEYWORDS = {
    "bạn là ai",
    "mày là ai",
    "bot là ai",
    "ai vậy",
    "tên gì",
    "giới thiệu bản thân",
    "who are you",
    "what are you",
    "your name",
    "introduce yourself",
}

COMPANY_KEYWORDS = {
    "công ty",
    "dịch vụ",
    "website",
    "contact",
    "software",
}


def _load_greetings() -> set[str]:
    global _greetings_cache
    words = {
        "hi",
        "hello",
        "chào",
        "xin chào",
        "thanks",
        "cảm ơn",
        "yo",
        "hey",
        "alo",
    }
    if GREETINGS_FILE.exists():
        try:
            text = GREETINGS_FILE.read_text(encoding="utf-8").lower()
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                for word in stripped.replace(",", " ").replace(".", " ").split():
                    cleaned = word.strip(",.!?")
                    if cleaned:
                        words.add(cleaned)
        except OSError:
            pass
    _greetings_cache = words
    return words


def is_greeting_or_thanks(message: str) -> bool:
    msg = message.strip().lower()
    if len(msg) > 150:
        return False
    if any(keyword in msg for keyword in COMPANY_KEYWORDS):
        return False
    if any(keyword in msg for keyword in IDENTITY_KEYWORDS):
        return True

    greetings = _greetings_cache or _load_greetings()
    return any(word in msg for word in greetings)


def get_quick_response(message: str = "", target_lang: str = "vi") -> str:
    msg_lower = message.strip().lower()
    if any(keyword in msg_lower for keyword in IDENTITY_KEYWORDS):
        return WHO_AM_I.get(target_lang, WHO_AM_I["vi"])

    responses = QUICK_RESPONSES.get(target_lang, QUICK_RESPONSES["vi"])
    return random.choice(responses)
