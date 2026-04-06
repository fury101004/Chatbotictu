# intent_engine.py – Phát hiện ý định người dùng (intent detection)
import random
from pathlib import Path

INTENTS_DIR = Path("data/intents")

# Cache để không phải đọc file liên tục
_cache = {}
_cache_mtime = {}

def _load_intent_file(filename: str) -> set:
    """Đọc file từ khóa, có cache để tăng tốc"""
    path = INTENTS_DIR / filename
    current_mtime = path.stat().st_mtime if path.exists() else None

    if filename in _cache and _cache_mtime.get(filename) == current_mtime:
        return _cache[filename]

    words = set()
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8").lower()
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    for word in line.replace(",", " ").split():
                        w = word.strip()
                        if w:
                            words.add(w)
        except Exception as e:
            print(f"[Intent] Lỗi đọc file {filename}: {e}")

    _cache[filename] = words
    _cache_mtime[filename] = current_mtime
    return words


# Load các file từ khóa
GREETINGS      = _load_intent_file("greetings.md")      # xin chào, hi, chào bạn...
CHITCHAT       = _load_intent_file("chitchat.md")       # hôm nay thế nào, ăn chưa...
LIGHT_INSULTS  = _load_intent_file("light_insults.md")  # ngu, đần, chậm hiểu...
HEAVY_INSULTS  = _load_intent_file("heavy_insults.md")  # đĩ, lồn, cặc, óc chó...


# Từ khóa hỏi danh tính – ưu tiên cực cao
INTRODUCTION_KEYWORDS = {
    "bạn là ai", "mày là ai", "bot là ai", "ai vậy", "là ai đấy", "là cái gì", "tên gì",
 "tên là gì", "gọi là gì", "tên mày là gì", "tên bạn là gì", "ai tạo ra mày", "ai làm ra bạn",
 "chủ của bạn là ai", "bạn được tạo bởi ai", "ai phát triển bạn", "who are you", "what are you",
 "you are what", "bạn làm gì", "bạn giúp gì được", "bạn hỗ trợ gì", "bạn biết gì"
}


# Trả lời chuyên nghiệp, tự nhiên, rõ ràng
RESPONSES = {
    "introduction": [
        "Mình là trợ lý ảo AI được thiết kế chuyên sâu để hỗ trợ bạn tra cứu kiến thức, giải đáp thắc mắc và đồng hành trong công việc/học tập.\n"
        "Mình có thể đọc hiểu tài liệu bạn upload (PDF, Markdown, Word...), nhớ toàn bộ lịch sử trò chuyện và trả lời cực kỳ chính xác dựa trên dữ liệu đó.\n"
        "Bạn cứ hỏi thoải mái – từ lập trình, học tập, đến cuộc sống thường ngày – mình đều hỗ trợ hết!",

        "Chào bạn! Mình là một trợ lý AI thông minh, được xây dựng để trở thành người bạn đồng hành đáng tin cậy của bạn.\n"
        "Điểm mạnh của mình là:\n"
        "• Đọc và hiểu tài liệu bạn cung cấp\n"
        "• Nhớ chính xác những gì chúng ta đã nói\n"
        "• Trả lời nhanh, đúng trọng tâm, không lan man\n"
        "Cứ thử hỏi mình bất kỳ điều gì nhé!",

        "Mình là trợ lý AI chuyên hỗ trợ tra cứu kiến thức cá nhân và doanh nghiệp.\n"
        "Bạn có thể nghĩ mình như một 'người thư ký thông minh' – luôn sẵn sàng tìm thông tin, giải thích rõ ràng, và không bao giờ quên những gì bạn đã hỏi.\n"
        "Rất vui được hỗ trợ bạn!",

        "Xin chào! Mình là một AI được huấn luyện để giúp bạn học tập, làm việc và giải quyết vấn đề hiệu quả hơn.\n"
        "Mình có thể:\n"
        "– Trả lời câu hỏi dựa trên tài liệu bạn upload\n"
        "– Nhớ toàn bộ cuộc trò chuyện\n"
        "– Hiểu khi bạn nói 'sai rồi', 'trả lời lại đi' và tự sửa ngay\n"
        "Bạn cần mình giúp gì hôm nay?"
    ],

    "greeting": [
        "Chào bạn! Rất vui được gặp lại",
        "Hi! Hôm nay bạn khỏe không?",
        "Xin chào! Mình luôn sẵn sàng hỗ trợ bạn",
        "Hello! Có gì mình giúp được không ạ?",
        "Chào! Hôm nay bạn muốn tìm hiểu gì nào?",
    ],

    "goodbye": [
        "Tạm biệt bạn! Chúc một ngày tốt lành",
        "Hẹn gặp lại nhé! Có gì cứ gọi mình",
        "Bye! Nghỉ ngơi vui vẻ nha",
        "Chúc ngủ ngon! Mai gặp lại",
        "Tạm biệt! Mình luôn ở đây khi bạn cần",
    ],

    "thanks": [
        "Không có gì! Rất vui được giúp bạn",
        "Rất hân hạnh được hỗ trợ",
        "Mình luôn sẵn sàng giúp bạn mà",
        "Có gì đâu, bạn cứ hỏi thoải mái nhé!",
        "Rất vui vì đã giúp được bạn",
    ],

    "light_insult": [
        "Ừm… mình sẽ cố gắng trả lời tốt hơn nhé",
        "Mình xin lỗi nếu làm bạn chưa hài lòng. Bạn muốn mình giải thích lại không?",
        "Mình còn đang học mỗi ngày. Cảm ơn bạn đã góp ý!",
        "Hihi, mình sẽ cố không để bạn phải nói thế lần nữa",
    ],

    "heavy_insult": [
        "Mình rất tiếc vì đã làm bạn khó chịu. Nếu có thể, bạn cho mình biết mình sai ở đâu để sửa nhé?",
        "Mình xin lỗi. Mình sẽ cố gắng trả lời tốt hơn trong tương lai.",
        "Mình hiểu bạn đang không vui. Nếu bạn muốn, mình sẵn sàng trả lời lại từ đầu.",
    ],

    "chitchat": [
        "Hôm nay thời tiết thế nào bên bạn?",
        "Bạn đang làm gì thú vị gần đây không?",
        "Cuối tuần này bạn có kế hoạch gì chưa?",
        "Mình vừa được cập nhật thêm nhiều kiến thức mới đấy!",
        "Bạn thích trà hay cà phê hơn?",
    ]
}


def detect_intent(message: str):
    """Phát hiện nhanh ý định người dùng – ưu tiên cao đến thấp"""
    msg = message.lower().strip()

    # 1. Chửi nặng → ưu tiên cao nhất
    if any(word in msg for word in HEAVY_INSULTS):
        return "heavy_insult"

    # 2. Hỏi danh tính → ưu tiên cực cao (người dùng hay hỏi nhất)
    if any(phrase in msg for phrase in INTRODUCTION_KEYWORDS):
        return "introduction"

    # 3. Chửi nhẹ
    if any(word in msg for word in LIGHT_INSULTS):
        return "light_insult"

    # 4. Tạm biệt
    goodbye_keywords = {"bye", "tạm biệt", "ngủ ngon", "ngủ đây", "đi ngủ", "good night", "bai", "hẹn gặp lại"}
    if any(word in msg for word in goodbye_keywords):
        return "goodbye"

    # 5. Cảm ơn
    thanks_keywords = {"cảm ơn", "thanks", "tks", "cám ơn", "thank you", "cảm ơn nhé", "ok cảm ơn"}
    if any(word in msg for word in thanks_keywords):
        return "thanks"

    # 6. Chào hỏi
    if any(word in msg for word in GREETINGS):
        return "greeting"

    # 7. Tán gẫu
    if any(word in msg for word in CHITCHAT):
        return "chitchat"

    # Không nhận diện được → để RAG xử lý
    return None


def get_intent_response(intent_type: str) -> str:
    """Trả về câu trả lời ngẫu nhiên theo intent"""
    if intent_type in RESPONSES:
        return random.choice(RESPONSES[intent_type])
    return random.choice(RESPONSES["chitchat"])
