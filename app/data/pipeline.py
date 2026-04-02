"""Prepare clean corpora and vector stores for the 3-agent student assistant."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import sys
import threading
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, DefaultDict, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from langchain_core.documents import Document
except Exception:  # pragma: no cover - compatibility fallback
    from langchain.schema import Document  # type: ignore[no-redef]

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except Exception:  # pragma: no cover - compatibility fallback
    from langchain.text_splitter import RecursiveCharacterTextSplitter  # type: ignore[no-redef]
from langchain_community.vectorstores import FAISS

try:
    from langchain_core.embeddings import Embeddings
except Exception:  # pragma: no cover - compatibility fallback
    class Embeddings:  # type: ignore[no-redef]
        pass

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover - optional runtime dependency
    SentenceTransformer = None  # type: ignore[assignment]

from app.core.config import EMBEDDINGS_MODEL, RAG_MD_DIR, TXT_DATA_DIR, VECTOR_DB_DIR


ROUTES: Tuple[str, ...] = ("handbook", "policy", "faq")
ROUTE_LABELS = {
    "handbook": "Agent Sổ tay sinh viên",
    "policy": "Agent Chính sách - Công văn - Quyết định",
    "faq": "Agent Câu hỏi sinh viên thường dùng",
}

FAQ_TOPIC_CONFIG = {
    "email": {
        "title": "Câu hỏi thường gặp về email sinh viên",
        "keywords": ["email trường", "mail ictu", "tài khoản email", "email sinh viên"],
        "faq_items": [
            {
                "question": "Email sinh viên được dùng trong những việc gì?",
                "answers": [
                    "Dùng cho thông báo học vụ, hệ thống học tập và các dịch vụ do trường cấp.",
                    "Nên ưu tiên dùng email trường khi làm việc với đơn vị trong trường hoặc nhận thông báo chính thức.",
                    "Nếu cần hướng dẫn cụ thể, hãy nói rõ dịch vụ hoặc hệ thống đang gặp vấn đề.",
                ],
            },
            {
                "question": "Khi nào bắt buộc phải sử dụng email do trường cấp?",
                "answers": [
                    "Khi truy cập các nền tảng chỉ dành cho người học hoặc nhận thông báo chính thức từ nhà trường.",
                    "Một số thủ tục và dịch vụ chỉ chấp nhận tài khoản email sinh viên do trường cấp.",
                    "Nếu văn bản áp dụng theo năm học, cần nói rõ năm học để tra cứu đúng căn cứ.",
                ],
            },
            {
                "question": "Cần lưu ý gì về bảo mật và lưu trữ dữ liệu trên email trường?",
                "answers": [
                    "Không chia sẻ mật khẩu và nên bật các lớp bảo mật nếu hệ thống hỗ trợ.",
                    "Cần kiểm tra đúng người gửi và liên kết trước khi cung cấp thông tin cá nhân.",
                    "Nên tuân thủ quy định lưu trữ, sao lưu và sử dụng email đúng mục đích học tập.",
                ],
            },
        ],
    },
    "bhyt": {
        "title": "Câu hỏi thường gặp về bảo hiểm y tế",
        "keywords": ["bhyt", "bảo hiểm y tế", "thẻ bhyt", "đóng bhyt"],
        "faq_items": [
            {
                "question": "Sinh viên đóng BHYT vào thời gian nào?",
                "answers": [
                    "Cần tra cứu theo thông báo BHYT của từng năm học và từng lần thu.",
                    "Mốc đóng có thể thay đổi theo đợt, vì vậy cần xác định đúng năm học hoặc học kỳ.",
                    "Nếu chưa rõ đợt nào, chatbot nên hỏi thêm khóa, hệ đào tạo hoặc thông tin liên quan.",
                ],
            },
            {
                "question": "Thông báo BHYT mới nhất đang áp dụng cho năm học nào?",
                "answers": [
                    "Ưu tiên thông báo có năm học gần nhất trong kho dữ liệu.",
                    "Cần đối chiếu số thông báo, năm ban hành và nếu có thì cả lần bổ sung hoặc lần 2, lần 3.",
                    "Khi cần căn cứ cụ thể, chatbot nên dẫn người dùng sang văn bản gốc.",
                ],
            },
            {
                "question": "Cần hỏi thêm thông tin gì để chatbot tra cứu đúng đợt đóng BHYT?",
                "answers": [
                    "Nên có năm học hoặc học kỳ đang cần tra cứu.",
                    "Nếu có, hãy bổ sung khóa, hệ đào tạo hoặc đối tượng áp dụng.",
                    "Thêm số thông báo hoặc lần thông báo sẽ giúp chatbot tìm nhanh và đúng hơn.",
                ],
            },
        ],
    },
    "scholarship": {
        "title": "Câu hỏi thường gặp về học bổng",
        "keywords": ["học bổng", "kkht", "học bổng khuyến khích học tập", "học bổng tài trợ"],
        "faq_items": [
            {
                "question": "Điều kiện xét học bổng KKHT là gì?",
                "answers": [
                    "Điều kiện thường phụ thuộc quy chế và thông báo hoặc quyết định của từng đợt xét.",
                    "Cần đối chiếu đúng học kỳ, năm học và đối tượng áp dụng.",
                    "Khi tra cứu cho cá nhân, nên cung cấp thêm khóa, lớp hoặc học kỳ liên quan.",
                ],
            },
            {
                "question": "Cần tra cứu công văn hay quyết định học bổng của đợt nào?",
                "answers": [
                    "Ưu tiên văn bản mới nhất gắn với học kỳ hoặc năm học đang hỏi.",
                    "Nếu có cả thông báo và quyết định, cần đối chiếu cả điều kiện xét và kết quả của từng đợt.",
                    "Khi cần căn cứ chính xác, chatbot nên dẫn người dùng sang văn bản gốc.",
                ],
            },
            {
                "question": "Khi hỏi chatbot, có nên nói rõ khóa và học kỳ không?",
                "answers": [
                    "Có, vì học bổng thường được xét theo học kỳ và năm học.",
                    "Thông tin này giúp lọc đúng đợt và tránh nhầm với các lần xét khác.",
                    "Nếu có, hãy bổ sung thêm hệ đào tạo hoặc đối tượng áp dụng.",
                ],
            },
        ],
    },
    "tuition": {
        "title": "Câu hỏi thường gặp về học phí và miễn giảm",
        "keywords": ["học phí", "miễn giảm học phí", "mghp", "hỗ trợ chi phí học tập"],
        "faq_items": [
            {
                "question": "Mức thu học phí theo năm học nào?",
                "answers": [
                    "Mức thu học phí thay đổi theo từng năm học và từng hệ đào tạo.",
                    "Cần nói rõ năm học, chương trình và hệ đào tạo để tra cứu đúng mức thu.",
                    "Nếu có văn bản sửa đổi hoặc bổ sung, ưu tiên bản mới nhất đang áp dụng.",
                ],
            },
            {
                "question": "Sinh viên thuộc diện miễn giảm cần căn cứ theo văn bản nào?",
                "answers": [
                    "Cần xem quy định chính sách miễn giảm và thông báo áp dụng theo từng năm học.",
                    "Đối tượng miễn giảm có thể cần đối chiếu thêm với văn bản nhà nước hoặc quy định của trường.",
                    "Khi cần kết luận cụ thể, chatbot nên dẫn sang văn bản gốc để đối chiếu.",
                ],
            },
            {
                "question": "Cần nói rõ hệ đào tạo và năm học nào khi tra cứu học phí?",
                "answers": [
                    "Có, vì mức thu khác nhau theo hệ đào tạo và năm học.",
                    "Nếu là chương trình đặc thù, cần nêu rõ loại hình đào tạo đang theo học.",
                    "Bổ sung học kỳ nếu đang cần tra cứu theo đợt thu cụ thể.",
                ],
            },
        ],
    },
    "benefit": {
        "title": "Câu hỏi thường gặp về chế độ chính sách sinh viên",
        "keywords": ["chế độ chính sách", "trợ cấp xã hội", "hỗ trợ chi phí học tập", "miễn giảm"],
        "faq_items": [
            {
                "question": "Sinh viên cần tra cứu nhóm chế độ nào: TCXH, HTHT hay miễn giảm học phí?",
                "answers": [
                    "Cần xác định đúng nhóm chính sách trước khi tra cứu.",
                    "Mỗi nhóm có điều kiện, hồ sơ và văn bản áp dụng riêng.",
                    "Nếu chưa rõ thuộc nhóm nào, chatbot nên hỏi thêm hoàn cảnh hoặc diện đối tượng.",
                ],
            },
            {
                "question": "Văn bản nào là căn cứ chính cho từng học kỳ?",
                "answers": [
                    "Ưu tiên thông báo hoặc quyết định áp dụng cho học kỳ và năm học đang hỏi.",
                    "Một số chế độ có thêm quy định khung và văn bản triển khai theo từng đợt.",
                    "Khi cần tra cứu chính xác, cần đối chiếu số văn bản và thời gian ban hành.",
                ],
            },
            {
                "question": "Khi hỏi chatbot, có cần nói rõ học kỳ và năm học hay không?",
                "answers": [
                    "Có, vì chế độ chính sách thường được xét theo học kỳ và năm học.",
                    "Thông tin này giúp lọc đúng đợt tiếp nhận hồ sơ và văn bản đang áp dụng.",
                    "Nếu có, hãy bổ sung thêm khóa và hệ đào tạo để tránh nhầm đối tượng.",
                ],
            },
        ],
    },
    "graduation": {
        "title": "Câu hỏi thường gặp về xét tốt nghiệp",
        "keywords": ["tốt nghiệp", "xét tốt nghiệp", "quyết định tốt nghiệp", "kế hoạch tốt nghiệp"],
        "faq_items": [
            {
                "question": "Cần xem kế hoạch xét tốt nghiệp hay quyết định công nhận tốt nghiệp?",
                "answers": [
                    "Nếu cần điều kiện và mốc thời gian, hãy xem kế hoạch xét tốt nghiệp.",
                    "Nếu cần kết quả chính thức, hãy xem quyết định công nhận tốt nghiệp.",
                    "Chatbot nên hỏi rõ mục đích tra cứu để dẫn đúng văn bản.",
                ],
            },
            {
                "question": "Thông tin quan trọng khi hỏi là năm, đợt xét và hệ đào tạo nào?",
                "answers": [
                    "Cần nói rõ năm, đợt xét và hệ đào tạo đang tra cứu.",
                    "Nhiều đợt xét có thể diễn ra trong cùng một năm học nên thông tin này rất quan trọng.",
                    "Thông tin đầy đủ giúp tìm đúng kế hoạch và quyết định liên quan.",
                ],
            },
            {
                "question": "Nếu cần tra cứu quyết định cấp bằng, nên nói rõ khóa nào?",
                "answers": [
                    "Nên nói rõ khóa hoặc khóa học nếu văn bản được tách theo từng đối tượng.",
                    "Có thể bổ sung thêm đợt xét hoặc thời gian dự kiến nhận bằng.",
                    "Nếu cần căn cứ pháp lý, ưu tiên dẫn đến văn bản gốc của trường.",
                ],
            },
        ],
    },
    "conduct": {
        "title": "Câu hỏi thường gặp về điểm rèn luyện",
        "keywords": ["điểm rèn luyện", "drl", "xét điểm rèn luyện"],
        "faq_items": [
            {
                "question": "Công văn xét điểm rèn luyện thuộc học kỳ nào?",
                "answers": [
                    "Điểm rèn luyện thường được thông báo theo học kỳ và năm học.",
                    "Cần nói rõ học kỳ đang tra cứu để tìm đúng công văn.",
                    "Nếu có nhiều lần bổ sung, ưu tiên văn bản mới nhất của đợt đó.",
                ],
            },
            {
                "question": "Cần biết năm học và đợt xét nào để tra cứu đúng?",
                "answers": [
                    "Có, vì cùng một chủ đề có thể có nhiều đợt xét trong một năm học.",
                    "Năm học giúp phân biệt quy định đang áp dụng.",
                    "Đợt xét giúp truy đúng thông báo hoặc hướng dẫn liên quan.",
                ],
            },
            {
                "question": "Căn cứ quy định đánh giá kết quả rèn luyện nào đang được áp dụng?",
                "answers": [
                    "Ưu tiên quy định chung về đánh giá rèn luyện và văn bản triển khai gần nhất.",
                    "Nếu cần kết luận về tiêu chí, chatbot nên dẫn sang văn bản gốc.",
                    "Chatbot có thể tóm tắt nhanh, nhưng vẫn nên giữ căn cứ đối chiếu.",
                ],
            },
        ],
    },
    "procedure": {
        "title": "Câu hỏi thường gặp về thủ tục và hồ sơ sinh viên",
        "keywords": ["thủ tục", "hồ sơ sinh viên", "thẻ sinh viên", "một cửa", "giấy xác nhận"],
        "faq_items": [
            {
                "question": "Thủ tục này nên hỏi theo sổ tay hay theo quyết định/quy định?",
                "answers": [
                    "Thủ tục cơ bản có thể xem trong sổ tay sinh viên.",
                    "Nếu cần biểu mẫu, đầu mối hoặc căn cứ bắt buộc, nên ưu tiên quyết định và quy định.",
                    "Chatbot nên xác định người dùng cần tổng quan hay cần hướng dẫn chi tiết.",
                ],
            },
            {
                "question": "Sinh viên cần nói rõ đang cần hồ sơ gì để chatbot hướng dẫn đúng?",
                "answers": [
                    "Nên nói rõ tên hồ sơ hoặc giấy tờ cần xin.",
                    "Bổ sung mục đích sử dụng nếu thủ tục phụ thuộc từng trường hợp.",
                    "Nếu có hạn nộp hoặc nơi nộp, chatbot sẽ dễ dẫn hướng dẫn hơn khi biết bối cảnh.",
                ],
            },
            {
                "question": "Nếu có liên quan đến thẻ sinh viên, hồ sơ, email thì nên nêu thêm thông tin nào?",
                "answers": [
                    "Nên nêu rõ loại vấn đề đang gặp và dịch vụ liên quan.",
                    "Có thể thêm khóa, lớp hoặc hệ đào tạo nếu thủ tục tách đối tượng.",
                    "Nếu đã có thông báo hoặc mẫu đơn, hãy đưa thêm tên văn bản để tra cứu nhanh hơn.",
                ],
            },
        ],
    },
    "employment": {
        "title": "Câu hỏi thường gặp về việc làm và doanh nghiệp",
        "keywords": ["việc làm", "tuyển dụng", "doanh nghiệp", "hội thảo nghề nghiệp"],
        "faq_items": [
            {
                "question": "Thông báo này là từ doanh nghiệp nào và năm nào?",
                "answers": [
                    "Nên xác định tên doanh nghiệp và thời gian ban hành thông báo.",
                    "Các thông báo việc làm thường thay đổi theo từng đợt tuyển dụng.",
                    "Thông tin này giúp lọc đúng bản tin liên quan nhanh hơn.",
                ],
            },
            {
                "question": "Cần phân biệt giữa thư ngỏ, kế hoạch hợp tác và thông báo tuyển dụng?",
                "answers": [
                    "Thư ngỏ và kế hoạch hợp tác thường mang tính thông tin hoặc chương trình.",
                    "Thông báo tuyển dụng tập trung vào vị trí, điều kiện và cách ứng tuyển.",
                    "Chatbot nên hỏi rõ người dùng cần cơ hội việc làm hay cần hiểu bối cảnh hợp tác.",
                ],
            },
            {
                "question": "Chatbot cần tên công ty hoặc thời gian để tìm đúng văn bản không?",
                "answers": [
                    "Có, ít nhất nên có tên công ty hoặc năm.",
                    "Nếu biết thêm tháng hoặc đợt sự kiện, kết quả tra cứu sẽ chính xác hơn.",
                    "Khi cần đối chiếu, chatbot nên dẫn đến văn bản gốc của doanh nghiệp hoặc nhà trường.",
                ],
            },
        ],
    },
    "handbook_general": {
        "title": "Câu hỏi thường gặp về sổ tay sinh viên",
        "keywords": ["sổ tay sinh viên", "cẩm nang sinh viên", "quy định học vụ cơ bản"],
        "faq_items": [
            {
                "question": "Sổ tay sinh viên gồm các phần nào?",
                "answers": [
                    "Thường gồm thông tin giới thiệu, học vụ, dịch vụ, quyền và nghĩa vụ sinh viên.",
                    "Các mục có thể thay đổi nhẹ theo từng năm học.",
                    "Chatbot có thể dẫn đến phần phù hợp nếu người dùng nói rõ nhu cầu.",
                ],
            },
            {
                "question": "Cần tra cứu thông tin tổng quan, đầu mối liên hệ hay quy trình học vụ cơ bản?",
                "answers": [
                    "Sổ tay phù hợp cho thông tin tổng quan và đầu mối liên hệ.",
                    "Các quy trình học vụ cơ bản cũng thường được tóm tắt trong sổ tay.",
                    "Nếu cần căn cứ chi tiết hơn, chatbot có thể chuyển sang văn bản chính sách.",
                ],
            },
            {
                "question": "Năm học của sổ tay có quan trọng khi đặt câu hỏi hay không?",
                "answers": [
                    "Có, vì thông tin liên hệ và một số quy định có thể được cập nhật theo năm học.",
                    "Khi hỏi chatbot, nên nói rõ năm học nếu muốn tra cứu chính xác.",
                    "Nếu không biết năm học, chatbot nên ưu tiên sổ tay gần nhất.",
                ],
            },
        ],
    },
}

ROUTE_HINTS = {
    "handbook": (
        "so tay sinh vien",
        "cam nang sinh vien",
    ),
}

FAQ_TOPIC_HINTS = {
    "email": ("email", "mail ictu", "tai khoan email"),
    "bhyt": ("bhyt", "bao hiem y te"),
    "scholarship": ("hoc bong", "kkht"),
    "tuition": ("hoc phi", "muc thu hoc phi"),
    "benefit": ("che do chinh sach", "tro cap xa hoi", "ho tro chi phi hoc tap", "mien giam"),
    "graduation": ("tot nghiep", "xet tot nghiep", "qd tot nghiep"),
    "conduct": ("diem ren luyen", "xet diem ren luyen", "drl"),
    "procedure": ("the sinh vien", "ho so sinh vien", "mot cua", "thu tuc", "giay xac nhan"),
    "employment": ("tuyen dung", "viec lam", "doanh nghiep"),
    "handbook_general": ("so tay sinh vien",),
}

NOISE_EXACT_PATTERNS = (
    re.compile(r"^\s*##\s*Chunk\s+\d+\s*:.*$", re.IGNORECASE),
    re.compile(r"^\s*noi dung\s+trang\b.*$", re.IGNORECASE),
    re.compile(r"^\s*muc luc\s*$", re.IGNORECASE),
    re.compile(r"^\s*trang\s+\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*[-=_*]{4,}\s*$"),
)

NOISE_FRAGMENT_HINTS = (
    "tai lieu nay thuoc so huu",
    "pham thi huong_",
    "da ky",
    "so va ky hieu",
    "doc lap tu do hanh phuc",
)

SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=900,
    chunk_overlap=180,
    separators=["\n## ", "\n# ", "\n\n", "\n", ". ", " ", ""],
)

_VECTOR_RUNTIME_LOCK = threading.RLock()
_VECTOR_DB_CACHE: Optional[Dict[str, FAISS]] = None
_VECTOR_DB_SIGNATURE: Optional[Tuple[Tuple[str, bool, int, int], ...]] = None
_RETRIEVER_CACHE: Dict[int, Dict[str, Any]] = {}


class LocalHashEmbeddings(Embeddings):
    """Deterministic local fallback when sentence-transformers is unavailable."""

    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    def _tokenize(self, text: str) -> List[str]:
        normalized = _normalize_lookup_text(text)
        return re.findall(r"[a-z0-9]+", normalized)

    def _embed(self, text: str) -> List[float]:
        vector = [0.0] * self.dimension
        tokens = self._tokenize(text)

        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha1(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = -1.0 if digest[4] % 2 else 1.0
            weight = 1.0 + (min(len(token), 12) / 12.0)
            vector[index] += sign * weight

        norm = math.sqrt(sum(value * value for value in vector))
        if not norm:
            return vector

        return [value / norm for value in vector]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._embed(text)


class SentenceTransformerEmbeddings(Embeddings):
    """Local sentence-transformers wrapper without LangChain deprecation warnings."""

    def __init__(self, model_name: str):
        if SentenceTransformer is None:
            raise RuntimeError("sentence-transformers is unavailable.")

        self._model = SentenceTransformer(model_name)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        vectors = self._model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def embed_query(self, text: str) -> List[float]:
        vector = self._model.encode(
            [text],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vector[0].tolist()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _normalize_lookup_text(*parts: str) -> str:
    joined = " ".join(part for part in parts if part)
    normalized = unicodedata.normalize("NFKD", joined)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    return re.sub(r"\s+", " ", normalized).strip()


def _split_frontmatter(raw_text: str) -> Tuple[Dict[str, str], str]:
    if not raw_text.startswith("---"):
        return {}, raw_text

    parts = raw_text.split("---", 2)
    if len(parts) < 3:
        return {}, raw_text

    raw_meta = parts[1]
    body = parts[2].lstrip()
    metadata: Dict[str, str] = {}

    for line in raw_meta.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")

    return metadata, body


def _dump_frontmatter(metadata: Dict[str, Any]) -> str:
    ordered_keys = [
        "doc_id",
        "title",
        "route",
        "agent_label",
        "topic",
        "category",
        "source_file",
        "source_md",
        "source_type",
        "year",
        "language",
        "created_at",
    ]

    lines = ["---"]
    seen = set()
    for key in ordered_keys:
        value = metadata.get(key, "")
        if value in ("", None):
            continue
        safe_value = str(value).replace('"', "'")
        lines.append(f'{key}: "{safe_value}"')
        seen.add(key)

    for key in sorted(metadata):
        if key in seen:
            continue
        value = metadata[key]
        if value in ("", None):
            continue
        safe_value = str(value).replace('"', "'")
        lines.append(f'{key}: "{safe_value}"')

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _is_noise_line(line: str) -> bool:
    stripped = line.strip()
    normalized = _normalize_lookup_text(stripped)

    if not stripped:
        return False

    for pattern in NOISE_EXACT_PATTERNS:
        if pattern.match(stripped):
            return True

    if stripped.count("") or stripped.count("") or stripped.count(""):
        return True

    if len(stripped) > 180:
        digit_tokens = re.findall(r"\b\d{1,4}[/:.-]?\d{0,4}\b", stripped)
        if len(digit_tokens) >= 8 and any(hint in normalized for hint in ("trang", "ngay", "ban hanh")):
            return True

    if any(fragment in normalized for fragment in NOISE_FRAGMENT_HINTS):
        repeated_dates = len(re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]20\d{2}\b", stripped))
        repeated_times = len(re.findall(r"_[0-2]?\d:\d{2}", stripped))
        if len(stripped) > 120 or repeated_dates >= 2 or repeated_times >= 2:
            return True

    if normalized.startswith("noi nhan") and len(stripped) < 30:
        return True

    return False


def _collapse_blanks(lines: Iterable[str]) -> List[str]:
    collapsed: List[str] = []
    previous_blank = False

    for line in lines:
        is_blank = not line.strip()
        if is_blank:
            if previous_blank:
                continue
            collapsed.append("")
        else:
            collapsed.append(line)
        previous_blank = is_blank

    while collapsed and not collapsed[0].strip():
        collapsed.pop(0)
    while collapsed and not collapsed[-1].strip():
        collapsed.pop()

    return collapsed


def _clean_markdown_body(body: str) -> str:
    body = body.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    cleaned_lines: List[str] = []
    previous_normalized = ""

    for raw_line in body.split("\n"):
        line = raw_line.strip()

        if _is_noise_line(line):
            continue

        if not line:
            cleaned_lines.append("")
            previous_normalized = ""
            continue

        line = re.sub(r"\s+", " ", line).strip()
        normalized = _normalize_lookup_text(line)

        if normalized and normalized == previous_normalized:
            continue

        if normalized.startswith("noi dung trang"):
            continue

        if len(re.findall(r"\b\d{1,4}\b", line)) >= 10 and "phan" in normalized and "chuong" in normalized:
            continue

        cleaned_lines.append(line)
        previous_normalized = normalized

    collapsed = _collapse_blanks(cleaned_lines)
    return "\n".join(collapsed).strip()


def _relative_markdown_path(path: Path) -> str:
    try:
        return str(path.relative_to(RAG_MD_DIR)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _build_doc_id(route: str, relative_path: str) -> str:
    normalized = _normalize_lookup_text(route, relative_path)
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")


def infer_route_from_metadata(metadata: Dict[str, Any]) -> str:
    text = _normalize_lookup_text(
        str(metadata.get("route", "")),
        str(metadata.get("category", "")),
        str(metadata.get("title", "")),
        str(metadata.get("source_file", "")),
        str(metadata.get("source_md", "")),
        str(metadata.get("relative_path", "")),
    )

    for hint in ROUTE_HINTS["handbook"]:
        if hint in text:
            return "handbook"

    if text.startswith("faq ") or "/faq/" in str(metadata.get("source_md", "")).replace("\\", "/"):
        return "faq"

    return "policy"


def _infer_faq_topic(metadata: Dict[str, Any], body: str) -> str:
    text = _normalize_lookup_text(
        str(metadata.get("category", "")),
        str(metadata.get("title", "")),
        str(metadata.get("source_file", "")),
        str(metadata.get("source_md", "")),
        body[:3000],
    )

    for topic, hints in FAQ_TOPIC_HINTS.items():
        if any(hint in text for hint in hints):
            return topic

    return ""


def _clear_generated_route_dirs() -> None:
    TXT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for route in ROUTES:
        target = TXT_DATA_DIR / route
        if target.exists():
            shutil.rmtree(target)


def _write_agent_document(
    destination: Path,
    metadata: Dict[str, Any],
    body: str,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(_dump_frontmatter(metadata) + body.rstrip() + "\n", encoding="utf-8")


def _faq_topic_payload() -> DefaultDict[str, List[Dict[str, str]]]:
    return defaultdict(list)


def _collect_topic_source(
    topic_sources: DefaultDict[str, List[Dict[str, str]]],
    topic: str,
    metadata: Dict[str, Any],
) -> None:
    if not topic:
        return

    entry = {
        "title": str(metadata.get("title", "")),
        "year": str(metadata.get("year", "")),
        "source_file": str(metadata.get("source_file", "")),
        "route": str(metadata.get("route", "")),
    }

    if entry not in topic_sources[topic]:
        topic_sources[topic].append(entry)


def _build_faq_markdown(topic: str, sources: Sequence[Dict[str, str]]) -> str:
    config = FAQ_TOPIC_CONFIG[topic]
    lines = [f"# {config['title']}", "", "## Khi nên hỏi agent này", ""]
    lines.append("- Khi bạn hỏi một vấn đề quen thuộc, cần trả lời nhanh, dễ hiểu.")
    lines.append("- Khi câu hỏi cần thêm năm học, đợt, học kỳ hoặc số văn bản để tra cứu sâu hơn.")
    lines.append("")
    lines.append("## Câu hỏi và trả lời")
    lines.append("")

    for item in config["faq_items"]:
        lines.append(f"**Q:** {item['question']}")
        lines.append("")
        lines.append("**A:**")
        lines.append("")
        for answer in item["answers"]:
            lines.append(f"- {answer}")
        lines.append("")

    lines.append("## Từ khóa nên có trong câu hỏi")
    lines.append("")
    for keyword in config["keywords"]:
        lines.append(f"- {keyword}")

    lines.append("")
    lines.append("## Nguồn ưu tiên để đối chiếu")
    lines.append("")

    sorted_sources = sorted(
        sources,
        key=lambda item: (item.get("year", ""), item.get("title", "")),
        reverse=True,
    )

    for source in sorted_sources[:12]:
        year = source.get("year") or "không rõ năm"
        title = source.get("title") or "Tài liệu không tên"
        source_file = source.get("source_file") or "Không rõ nguồn"
        lines.append(f"- [{year}] {title} | {source_file}")

    if not sorted_sources:
        lines.append("- Kho dữ liệu chưa có tài liệu tham chiếu cụ thể cho chủ đề này.")

    lines.append("")
    lines.append("## Ghi chú cho chatbot")
    lines.append("")
    lines.append("- Nếu người dùng hỏi chưa đủ rõ, cần hỏi thêm năm học, học kỳ, khóa hoặc hệ đào tạo.")
    lines.append("- Ưu tiên dẫn nguồn sang văn bản chính thức trong kho policy khi cần căn cứ cụ thể.")

    return "\n".join(lines).strip() + "\n"


def _create_faq_documents(topic_sources: DefaultDict[str, List[Dict[str, str]]]) -> Counter:
    counts: Counter = Counter()

    for topic, config in FAQ_TOPIC_CONFIG.items():
        destination = TXT_DATA_DIR / "faq" / f"{topic}.md"
        metadata = {
            "doc_id": f"faq_{topic}",
            "title": config["title"],
            "route": "faq",
            "agent_label": ROUTE_LABELS["faq"],
            "topic": topic,
            "category": "faq_generated",
            "source_file": f"generated://faq/{topic}",
            "source_md": f"generated://faq/{topic}.md",
            "source_type": "generated",
            "language": "vi",
            "created_at": date.today().isoformat(),
        }
        body = _build_faq_markdown(topic, topic_sources.get(topic, []))
        _write_agent_document(destination, metadata, body)
        counts["faq"] += 1

    return counts


def prepare_agent_corpora() -> Dict[str, int]:
    if not RAG_MD_DIR.exists():
        raise FileNotFoundError(f"Không tìm thấy thư mục RAG_MD_DIR: {RAG_MD_DIR}")

    _clear_generated_route_dirs()

    counts: Counter = Counter()
    topic_sources = _faq_topic_payload()

    for source_path in sorted(RAG_MD_DIR.rglob("*.md")):
        raw_text = _read_text(source_path)
        metadata, body = _split_frontmatter(raw_text)

        relative_path = _relative_markdown_path(source_path)
        cleaned_body = _clean_markdown_body(body)
        if not cleaned_body:
            continue

        route = infer_route_from_metadata(
            {
                **metadata,
                "relative_path": relative_path,
                "source_md": relative_path,
            }
        )
        topic = _infer_faq_topic(metadata, cleaned_body)

        doc_metadata = {
            "doc_id": metadata.get("doc_id") or _build_doc_id(route, relative_path),
            "title": metadata.get("title") or source_path.stem,
            "route": route,
            "agent_label": ROUTE_LABELS[route],
            "topic": topic,
            "category": metadata.get("category", ""),
            "source_file": metadata.get("source_file") or relative_path,
            "source_md": relative_path,
            "source_type": metadata.get("source_type", "md"),
            "year": metadata.get("year", ""),
            "language": metadata.get("language", "vi"),
            "created_at": date.today().isoformat(),
        }

        destination = TXT_DATA_DIR / route / source_path.relative_to(RAG_MD_DIR)
        _write_agent_document(destination, doc_metadata, cleaned_body)
        counts[route] += 1
        _collect_topic_source(topic_sources, topic, doc_metadata)

        if route == "handbook":
            _collect_topic_source(topic_sources, "handbook_general", doc_metadata)

    counts.update(_create_faq_documents(topic_sources))

    manifest_path = TXT_DATA_DIR / "manifest.json"
    manifest_payload = {
        "generated_at": date.today().isoformat(),
        "counts": dict(counts),
        "topics": {topic: len(entries) for topic, entries in topic_sources.items()},
    }
    manifest_path.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {route: counts.get(route, 0) for route in ROUTES}


def _doc_from_markdown(path: Path, route: str) -> Optional[Document]:
    raw_text = _read_text(path)
    metadata, body = _split_frontmatter(raw_text)
    cleaned_body = _clean_markdown_body(body)
    if not cleaned_body:
        return None

    title = metadata.get("title") or path.stem
    topic = metadata.get("topic", "")
    prefix_lines = [f"Tieu de: {title}"]
    if topic:
        prefix_lines.append(f"Chu de: {topic}")

    page_content = "\n".join(prefix_lines) + "\n\n" + cleaned_body
    document_metadata = {
        "doc_id": metadata.get("doc_id") or _build_doc_id(route, str(path)),
        "title": title,
        "route": metadata.get("route") or route,
        "topic": topic,
        "category": metadata.get("category", ""),
        "year": metadata.get("year", ""),
        "source": metadata.get("source_file") or str(path),
        "source_file": metadata.get("source_file") or str(path),
        "source_md": metadata.get("source_md") or str(path),
        "agent_path": str(path),
    }
    return Document(page_content=page_content, metadata=document_metadata)


def load_docs_by_folder(folder: Path, route: str) -> List[Document]:
    documents: List[Document] = []

    if not folder.exists():
        return documents

    for path in sorted(folder.rglob("*.md")):
        document = _doc_from_markdown(path, route)
        if document is not None:
            documents.append(document)

    return documents


def chunk_docs(documents: Sequence[Document]) -> List[Document]:
    return SPLITTER.split_documents(list(documents))


def _vector_store_signature() -> Tuple[Tuple[str, bool, int, int], ...]:
    signature: List[Tuple[str, bool, int, int]] = []

    for route in ROUTES:
        route_dir = VECTOR_DB_DIR / route
        index_path = route_dir / "index.faiss"
        exists = index_path.exists()
        stat_target = index_path if exists else route_dir
        if stat_target.exists():
            stat = stat_target.stat()
            signature.append((route, True, stat.st_mtime_ns, stat.st_size))
        else:
            signature.append((route, False, 0, 0))

    legacy_index = VECTOR_DB_DIR / "index.faiss"
    legacy_meta = VECTOR_DB_DIR / "index.pkl"
    for legacy_name, legacy_path in (("legacy_faiss", legacy_index), ("legacy_meta", legacy_meta)):
        if legacy_path.exists():
            stat = legacy_path.stat()
            signature.append((legacy_name, True, stat.st_mtime_ns, stat.st_size))
        else:
            signature.append((legacy_name, False, 0, 0))

    return tuple(signature)


def invalidate_vector_runtime_cache() -> None:
    global _VECTOR_DB_CACHE, _VECTOR_DB_SIGNATURE

    with _VECTOR_RUNTIME_LOCK:
        _VECTOR_DB_CACHE = None
        _VECTOR_DB_SIGNATURE = None
        _RETRIEVER_CACHE.clear()


@lru_cache(maxsize=1)
def _ensure_embeddings() -> Embeddings:
    if SentenceTransformer is not None:
        try:
            return SentenceTransformerEmbeddings(model_name=EMBEDDINGS_MODEL)
        except Exception:
            pass

    print(
        "Cảnh báo: fallback sang LocalHashEmbeddings vì không khởi tạo được SentenceTransformerEmbeddings."
    )
    return LocalHashEmbeddings()


def build_multi_vector_db(*, invalidate_cache: bool = True) -> Dict[str, int]:
    embeddings = _ensure_embeddings()
    counts: Dict[str, int] = {}

    for route in ROUTES:
        folder = TXT_DATA_DIR / route
        documents = load_docs_by_folder(folder, route)
        if not documents:
            counts[route] = 0
            continue

        chunks = chunk_docs(documents)
        save_path = VECTOR_DB_DIR / route
        if save_path.exists():
            shutil.rmtree(save_path)
        save_path.mkdir(parents=True, exist_ok=True)

        db = FAISS.from_documents(chunks, embeddings)
        db.save_local(str(save_path))
        counts[route] = len(chunks)

    if invalidate_cache:
        invalidate_vector_runtime_cache()
    return counts


def load_multi_vector_db() -> Dict[str, FAISS]:
    global _VECTOR_DB_CACHE, _VECTOR_DB_SIGNATURE

    signature = _vector_store_signature()
    with _VECTOR_RUNTIME_LOCK:
        if _VECTOR_DB_CACHE is not None and _VECTOR_DB_SIGNATURE == signature:
            return _VECTOR_DB_CACHE

        embeddings = _ensure_embeddings()
        databases: Dict[str, FAISS] = {}

        for route in ROUTES:
            path = VECTOR_DB_DIR / route
            if not path.exists():
                continue
            databases[route] = FAISS.load_local(
                str(path),
                embeddings,
                allow_dangerous_deserialization=True,
            )

        legacy_index = VECTOR_DB_DIR / "index.faiss"
        legacy_meta = VECTOR_DB_DIR / "index.pkl"
        if not databases and legacy_index.exists() and legacy_meta.exists():
            databases["policy"] = FAISS.load_local(
                str(VECTOR_DB_DIR),
                embeddings,
                allow_dangerous_deserialization=True,
            )

        _VECTOR_DB_CACHE = databases
        _VECTOR_DB_SIGNATURE = signature
        _RETRIEVER_CACHE.clear()
        return databases


def get_multi_retriever(search_k: int = 10) -> Dict[str, Any]:
    with _VECTOR_RUNTIME_LOCK:
        if search_k in _RETRIEVER_CACHE:
            return _RETRIEVER_CACHE[search_k]

        retrievers = {
            route: database.as_retriever(search_kwargs={"k": search_k})
            for route, database in load_multi_vector_db().items()
        }
        _RETRIEVER_CACHE[search_k] = retrievers
        return retrievers


def _format_counts(title: str, counts: Dict[str, int]) -> str:
    parts = [f"{route}={counts.get(route, 0)}" for route in ROUTES]
    return f"{title}: " + ", ".join(parts)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    command = (args[0] if args else "build").strip().lower()

    if command == "prepare":
        counts = prepare_agent_corpora()
        print(_format_counts("Đã chia dữ liệu cho 3 agent", counts))
        return 0

    if command == "build":
        if not any((TXT_DATA_DIR / route).exists() for route in ROUTES):
            prepare_counts = prepare_agent_corpora()
            print(_format_counts("Đã chia dữ liệu cho 3 agent", prepare_counts))
        build_counts = build_multi_vector_db()
        print(_format_counts("Đã build vector stores", build_counts))
        return 0

    if command in {"rebuild", "all"}:
        prepare_counts = prepare_agent_corpora()
        build_counts = build_multi_vector_db()
        print(_format_counts("Đã chia dữ liệu cho 3 agent", prepare_counts))
        print(_format_counts("Đã build vector stores", build_counts))
        return 0

    if command == "stats":
        manifest_path = TXT_DATA_DIR / "manifest.json"
        if manifest_path.exists():
            print(manifest_path.read_text(encoding="utf-8"))
            return 0
        print("Chưa có manifest. Hãy chạy `python -m app.data.pipeline prepare` hoặc `build`.")
        return 1

    print("Lệnh không hợp lệ. Dùng: prepare | build | rebuild | stats")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
