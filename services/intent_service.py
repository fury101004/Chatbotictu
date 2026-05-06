from __future__ import annotations

import random
import re
import unicodedata
from pathlib import Path

from config.settings import settings


INTENTS_DIR = Path(settings.INTENTS_DIR)
_cache: dict[str, set[str]] = {}
_cache_mtime: dict[str, float | None] = {}
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_WORD_BOUNDARY_RE = re.compile(r"[a-z0-9]")
_SHORT_GREETING_TOKENS = {"hi", "yo", "ok", "alo", "hey"}


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or "").casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.replace("đ", "d")
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_keywords(values: set[str]) -> set[str]:
    return {item for item in (_normalize_text(value) for value in values) if item}


def _tokenize_words(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text))


def _keyword_in_message(message: str, tokens: set[str], keyword: str) -> bool:
    if not keyword:
        return False

    if _WORD_BOUNDARY_RE.search(keyword):
        if " " in keyword:
            pattern = rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])"
            return re.search(pattern, message) is not None

        if len(keyword) <= 2:
            return keyword in _SHORT_GREETING_TOKENS and keyword in tokens
        return keyword in tokens

    return keyword in message


def _contains_any(message: str, tokens: set[str], keywords: set[str]) -> bool:
    return any(_keyword_in_message(message, tokens, keyword) for keyword in keywords)


def _load_intent_file(filename: str) -> set[str]:
    path = INTENTS_DIR / filename
    current_mtime = path.stat().st_mtime if path.exists() else None

    if filename in _cache and _cache_mtime.get(filename) == current_mtime:
        return _cache[filename]

    phrases: set[str] = set()
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                for part in stripped.split(","):
                    phrase = _normalize_text(part)
                    if phrase:
                        phrases.add(phrase)
        except OSError:
            pass

    _cache[filename] = phrases
    _cache_mtime[filename] = current_mtime
    return phrases


GREETINGS = _load_intent_file("greetings.md")
CHITCHAT = _load_intent_file("chitchat.md")
LIGHT_INSULTS = _load_intent_file("light_insults.md")
HEAVY_INSULTS = _load_intent_file("heavy_insults.md")

INTRODUCTION_KEYWORDS = _normalize_keywords(
    {
        "ban la ai",
        "may la ai",
        "bot la ai",
        "ai vay",
        "la ai day",
        "ban ten gi",
        "ten ban la gi",
        "ten bot la gi",
        "gioi thieu ban than",
        "who are you",
        "what are you",
        "your name",
        "introduce yourself",
    }
)

GOODBYE_KEYWORDS = _normalize_keywords({"bye", "tam biet", "ngu ngon", "hen gap lai"})
THANKS_KEYWORDS = _normalize_keywords({"cam on", "thanks", "thank you", "ok cam on"})


RESPONSES = {
    "introduction": [
        "Mình là trợ lý AI của ICTU, chuyên hỗ trợ tra cứu và giải đáp thông tin cho sinh viên.",
    ],
    "greeting": [
        "Chào bạn! Mình sẵn sàng hỗ trợ đây.",
        "Xin chào! Bạn cần mình tra cứu gì nào?",
    ],
    "goodbye": [
        "Tạm biệt bạn! Khi cần cứ quay lại nhé.",
    ],
    "thanks": [
        "Không có gì, mình rất vui được hỗ trợ bạn.",
    ],
    "light_insult": [
        "Mình sẽ cố trả lời rõ hơn nhé. Bạn nói mình biết chỗ nào chưa ổn được không?",
    ],
    "heavy_insult": [
        "Nếu câu trả lời trước chưa đúng, bạn cho mình thêm chi tiết để mình sửa nhé.",
    ],
    "chitchat": [
        "Mình vẫn đang ở đây, bạn muốn hỏi gì về ICTU nào?",
    ],
}


def detect_intent(message: str) -> str | None:
    normalized_message = _normalize_text(message)
    tokens = _tokenize_words(normalized_message)

    if _contains_any(normalized_message, tokens, HEAVY_INSULTS):
        return "heavy_insult"
    if _contains_any(normalized_message, tokens, INTRODUCTION_KEYWORDS):
        return "introduction"
    if _contains_any(normalized_message, tokens, LIGHT_INSULTS):
        return "light_insult"

    if _contains_any(normalized_message, tokens, GOODBYE_KEYWORDS):
        return "goodbye"
    if _contains_any(normalized_message, tokens, THANKS_KEYWORDS):
        return "thanks"

    if _contains_any(normalized_message, tokens, GREETINGS):
        return "greeting"
    if _contains_any(normalized_message, tokens, CHITCHAT):
        return "chitchat"
    return None


def get_intent_response(intent_type: str) -> str:
    if intent_type in RESPONSES:
        return random.choice(RESPONSES[intent_type])
    return random.choice(RESPONSES["chitchat"])
