from pathlib import Path

from config.settings import settings

QA_ROOT = settings.QA_CORPUS_ROOT

RAG_TOOL_PROFILES = {
    "student_handbook_rag": {
        "label": "Hoi dap so tay sinh vien",
        "corpus_paths": [
            QA_ROOT / "Sổ tay sinh viên các năm",
        ],
        "route_keywords": [
            "sổ tay",
            "so tay",
            "cẩm nang",
            "cam nang",
            "handbook",
            "sinh viên khóa",
            "tân sinh viên",
            "tan sinh vien",
        ],
    },
    "school_policy_rag": {
        "label": "Chinh sach va quy dinh nha truong",
        "corpus_paths": [
            QA_ROOT / "Các Văn Bản Pháp Quy",
            QA_ROOT / "Các Văn Bản Quản Lý Nội Bộ",
            QA_ROOT / "Các Văn Quản Lý  Của Cơ Quan Chủ Quản",
            QA_ROOT / "congvanquyetdinh",
            QA_ROOT / "chedovachinhsach",
        ],
        "route_keywords": [
            "quy chế",
            "quy che",
            "quy định",
            "quy dinh",
            "quyết định",
            "quyet dinh",
            "thông tư",
            "thong tu",
            "nghị định",
            "nghi dinh",
            "luật",
            "luat",
            "chính sách",
            "chinh sach",
            "miễn giảm",
            "mghp",
            "trợ cấp",
            "học bổng",
            "học phí",
            "điểm rèn luyện",
            "đrl",
            "kỷ luật",
            "khen thưởng",
        ],
    },
    "student_faq_rag": {
        "label": "FAQ sinh vien thuong hoi",
        "corpus_paths": [
            QA_ROOT / "congvanxettn",
            QA_ROOT / "congvanvieclam",
            QA_ROOT / "congvanveemail",
            QA_ROOT,
        ],
        "route_keywords": [
            "khi nào",
            "khi nao",
            "bao giờ",
            "bao gio",
            "ở đâu",
            "o dau",
            "làm sao",
            "lam sao",
            "thế nào",
            "the nao",
            "email",
            "tốt nghiệp",
            "tot nghiep",
            "xét tốt nghiệp",
            "xet tot nghiep",
            "việc làm",
            "viec lam",
            "tuyển dụng",
            "tuyen dung",
            "hồ sơ",
            "ho so",
            "bảo hiểm",
            "bao hiem",
            "bhyt",
            "đăng ký",
            "dang ky",
        ],
    },
}

RAG_TOOL_ORDER = [
    "student_handbook_rag",
    "school_policy_rag",
    "student_faq_rag",
]
DEFAULT_RAG_TOOL = "student_faq_rag"
FALLBACK_RAG_NODE = "fallback_rag"

__all__ = [
    "QA_ROOT",
    "RAG_TOOL_PROFILES",
    "RAG_TOOL_ORDER",
    "DEFAULT_RAG_TOOL",
    "FALLBACK_RAG_NODE",
]

