from __future__ import annotations

import random
import re
from pathlib import Path

from config.settings import settings


BADWORDS_FILE = Path(settings.BADWORDS_PATH)
_badwords_cache: set[str] | None = None
_badword_pattern: re.Pattern[str] | None = None


def _load_badwords() -> set[str]:
    global _badwords_cache
    if _badwords_cache is not None:
        return _badwords_cache

    try:
        text = BADWORDS_FILE.read_text(encoding="utf-8")
        words = [
            line.strip().lower()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        _badwords_cache = set(words)
    except FileNotFoundError:
        _badwords_cache = {"đm", "dm", "cặc", "lồn", "vl", "ngu", "fuck", "shit"}
    return _badwords_cache


def get_badword_pattern() -> re.Pattern[str]:
    global _badword_pattern
    if _badword_pattern is None:
        words = _load_badwords()
        if words:
            pattern = r"\b(" + "|".join(map(re.escape, words)) + r")\b"
            _badword_pattern = re.compile(pattern, re.IGNORECASE)
        else:
            _badword_pattern = re.compile(r"^$")
    return _badword_pattern


SWIFT_RESPONSES = [
    "Mình hiểu bạn đang khó chịu. Nếu muốn, mình sẽ trả lời lại rõ hơn nhé.",
    "Mình ở đây để hỗ trợ bạn. Bạn nói rõ chỗ chưa đúng, mình sửa ngay.",
    "Nếu câu trước chưa ổn, bạn cho mình thêm chi tiết để mình trả lời chính xác hơn nhé.",
]


def contains_swear(message: str) -> bool:
    return bool(get_badword_pattern().search(message))


def get_swear_response() -> str:
    return random.choice(SWIFT_RESPONSES)
