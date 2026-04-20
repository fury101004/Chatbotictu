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
    "dai hoc cong nghe thong tin va truyen thong",
    "truong dai hoc cong nghe thong tin va truyen thong",
    "dai hoc cntt va tt",
    "dai hoc cntt&tt",
    "dh cntt va tt",
    "dhcntt",
    "dhcntt va tt",
    "cntt va tt thai nguyen",
    "cntt&tt thai nguyen",
    "dai hoc thai nguyen",
    "thai nguyen university",
)

ICTU_CONTEXT_MARKERS = (
    "sinh vien",
    "hoc vien",
    "tan sinh vien",
    "phu huynh",
    "giang vien",
    "co van hoc tap",
    "nha truong",
    "truong minh",
    "phong dao tao",
    "phong cong tac sinh vien",
    "ctsv",
    "so tay sinh vien",
    "so tay",
    "quy che",
    "quy dinh",
    "quyet dinh",
    "thong bao",
    "cong van",
    "hoc phi",
    "mien giam hoc phi",
    "hoc bong",
    "tin chi",
    "hoc phan",
    "chuong trinh dao tao",
    "chuan dau ra",
    "nganh dao tao",
    "khoa dao tao",
    "lop hoc phan",
    "dang ky hoc",
    "dang ky tin chi",
    "lich hoc",
    "lich thi",
    "diem ren luyen",
    "diem hoc tap",
    "hoc ky",
    "nam hoc",
    "tot nghiep",
    "xet tot nghiep",
    "thuc tap",
    "do an",
    "khoa luan",
    "bao hiem y te",
    "bhyt",
    "noi tru",
    "ngoai tru",
    "ky tuc xa",
    "email sinh vien",
    "tai khoan sinh vien",
    "cong thong tin",
    "tuyen dung",
    "viec lam",
    "huong nghiep",
    "hoi thao nghe nghiep",
    "fpt software",
    "canon",
)


def normalize_scope_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    stripped = stripped.replace("đ", "d")
    stripped = stripped.replace("&", " va ")
    return re.sub(r"\s+", " ", stripped).strip()


def is_ictu_related_query(text: str) -> bool:
    normalized = normalize_scope_text(text or "")
    if not normalized:
        return True

    if any(marker in normalized for marker in ICTU_EXPLICIT_MARKERS):
        return True

    return any(marker in normalized for marker in ICTU_CONTEXT_MARKERS)
