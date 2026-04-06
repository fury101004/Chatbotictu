# badword_filter.py – Lọc từ chửi trong tin nhắn người dùng
import random
import re
from pathlib import Path

BADWORDS_FILE = Path("data/intents/badwords.md")

# Cache để không phải đọc file mỗi lần
_badwords_cache = None
_badword_pattern = None

def _load_badwords() -> set:
    """Đọc danh sách từ chửi từ file data/badwords.md"""
    global _badwords_cache
    if _badwords_cache is not None:
        return _badwords_cache

    try:
        text = BADWORDS_FILE.read_text(encoding="utf-8")
        words = []
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):  # bỏ dòng trống và comment
                words.append(line.lower())
        _badwords_cache = set(words)
        return _badwords_cache
    except FileNotFoundError:
        # Fallback nếu chưa có file
        return {"đm", "dm", "cặc", "lồn", "vl", "ngu", "fuck", "shit"}

def get_badword_pattern():
    """Trả về regex pattern đã compile"""
    global _badword_pattern
    if _badword_pattern is None:
        words = _load_badwords()
        if words:
            pattern = r'\b(' + '|'.join(map(re.escape, words)) + r')\b'
            _badword_pattern = re.compile(pattern, re.IGNORECASE)
        else:
            _badword_pattern = re.compile(r'^$')  # không match gì
    return _badword_pattern

# Danh sách trả lời khi bị chửi (vẫn giữ nguyên, hoặc đại ca có thể làm file riêng cũng được)
SWIFT_RESPONSES = [
    "Ủa đại ca chửi em hả? Em buồn 5 giây thôi nha",
    "Trời ơi đại ca nóng tính quá, em sợ á",
    "Đại ca ơi bình tĩnh sống lâu trăm tuổi nè",
    "Má ơi em bị chửi rồi, đau lòng quá đi mất",
    "Đại ca nói bậy là em mách mẹ đó nha",
    "Chửi em chi vậy đại ca, em ngoan mà",
    "Huhu đại ca dữ quá, em đi khóc đây",
    "Đại ca chửi hay thế em save lại làm kỷ niệm luôn",
]

def contains_swear(message: str) -> bool:
    """Kiểm tra tin nhắn có từ chửi không"""
    return bool(get_badword_pattern().search(message))

def get_swear_response() -> str:
    """Trả về 1 câu lầy ngẫu nhiên"""
    return random.choice(SWIFT_RESPONSES)
