from __future__ import annotations

import re
import unicodedata


ICTU_SCOPE_REPLY_VI = (
    "Câu hỏi này nằm ngoài phạm vi ICTU. Hệ thống chỉ tìm kiếm và trả lời "
    "các nội dung liên quan đến Trường Đại học Công nghệ Thông tin và Truyền thông - "
    "Đại học Thái Nguyên."
)

ICTU_EXPLICIT_MARKERS = (
    "ictu",
    "Đại học Công nghệ Thông tin và Truyền thông",
    "Trường Đại học Công nghệ Thông tin và Truyền thông",
    "Đại học CNTT và TT",
    "Đại học CNTT&TT",
    "DH CNTT và TT",
    "DHCNTT",
    "CNTT và TT Thái Nguyên",
    "Thai Nguyen University",
)

ICTU_CONTEXT_MARKERS = (
    "sinh viên",
    "người học",
    "học viên",
    "tân sinh viên",
    "phụ huynh",
    "giảng viên",
    "cố vấn học tập",
    "nhà trường",
    "phòng đào tạo",
    "ctsv",
    "sổ tay sinh viên",
    "sổ tay",
    "quy chế",
    "quy định",
    "quyết định",
    "thông báo",
    "công văn",
    "học phí",
    "miễn giảm học phí",
    "học bổng",
    "tín chỉ",
    "học phần",
    "chương trình đào tạo",
    "chuẩn đầu ra",
    "ngành đào tạo",
    "khóa đào tạo",
    "đăng ký học",
    "đăng ký tín chỉ",
    "lịch học",
    "lịch thi",
    "điểm rèn luyện",
    "điểm học tập",
    "học kỳ",
    "năm học",
    "tốt nghiệp",
    "xét tốt nghiệp",
    "thực tập",
    "đồ án",
    "khóa luận",
    "bảo hiểm y tế",
    "bhyt",
    "nội trú",
    "ngoại trú",
    "ký túc xá",
    "email sinh viên",
    "tài khoản sinh viên",
    "cổng thông tin",
    "tuyển dụng",
    "việc làm",
    "hướng nghiệp",
)


def normalize_scope_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text or "").casefold())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    stripped = stripped.replace("đ", "d").replace("\u00c4\u2018", "d")
    stripped = stripped.replace("&", " va ")
    stripped = re.sub(r"[^\w\s]", " ", stripped, flags=re.UNICODE)
    return re.sub(r"\s+", " ", stripped).strip()


def _contains_any_marker(normalized_text: str, markers: tuple[str, ...]) -> bool:
    for marker in markers:
        marker_normalized = normalize_scope_text(marker)
        if marker_normalized and marker_normalized in normalized_text:
            return True
    return False


def is_ictu_related_query(text: str) -> bool:
    normalized = normalize_scope_text(text or "")
    if not normalized:
        return True

    if _contains_any_marker(normalized, ICTU_EXPLICIT_MARKERS):
        return True

    return _contains_any_marker(normalized, ICTU_CONTEXT_MARKERS)
