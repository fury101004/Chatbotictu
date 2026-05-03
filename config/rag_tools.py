from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Optional

from config.settings import settings

QA_ROOT = settings.QA_CORPUS_ROOT
RAG_UPLOAD_ROOT = settings.RAG_UPLOAD_ROOT
UPLOAD_SOURCE_PREFIX = "uploads"

RAG_TOOL_PROFILES = {
    "student_handbook_rag": {
        "label": "Sổ tay sinh viên",
        "description": "Sổ tay, cẩm nang tân sinh viên, thông tin tổng quan theo khóa, khóa học, chương trình, danh hiệu sinh viên Khá/Giỏi/Xuất sắc.",
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
            "danh hiệu sinh viên",
            "danh hieu sinh vien",
            "danh hiệu cá nhân",
            "danh hieu ca nhan",
            "nguoi hoc",
            "hanh vi",
            "khong duoc lam",
            "danh hieu",
            "khá giỏi xuất sắc",
            "kha gioi xuat sac",
            "xuất sắc",
            "xuat sac",
            "chuong trinh hoc",
            "chuong trinh dao tao",
            "ctdt",
            "tong so tin chi",
            "bao nhieu tin chi",
            "khoa 20",
            "khoa 21",
            "khoa 22",
            "khoa 23",
            "khoa 24",
            "k20",
            "k21",
            "k22",
            "k23",
            "k24",
        ],
    },
    "school_policy_rag": {
        "label": "Quy định và chính sách",
        "description": "Quy chế, quy định, quyết định, thông tư, học phí, học bổng, kỷ luật, điểm rèn luyện, chế độ chính sách.",
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
        "label": "FAQ sinh viên",
        "description": "Câu hỏi thường gặp về quy trình, email, hồ sơ, tốt nghiệp, việc làm, bảo hiểm, đăng ký, hỏi đáp tác vụ.",
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


def is_valid_rag_tool(tool_name: Optional[str]) -> bool:
    return bool(tool_name) and tool_name in RAG_TOOL_PROFILES


def get_tool_profile(tool_name: Optional[str]) -> dict:
    if is_valid_rag_tool(tool_name):
        return RAG_TOOL_PROFILES[str(tool_name)]
    return RAG_TOOL_PROFILES[DEFAULT_RAG_TOOL]


def get_tool_upload_dir(tool_name: str) -> Path:
    upload_dir = RAG_UPLOAD_ROOT / tool_name
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def get_tool_corpus_paths(tool_name: str) -> list[Path]:
    profile = get_tool_profile(tool_name)
    return [Path(path) for path in profile.get("corpus_paths", [])] + [get_tool_upload_dir(tool_name)]


def build_upload_source_name(tool_name: str, filename: str) -> str:
    return PurePosixPath(UPLOAD_SOURCE_PREFIX, tool_name, filename).as_posix()


def resolve_upload_source_path(source_name: str) -> Path:
    normalized = PurePosixPath(str(source_name).replace("\\", "/"))
    if len(normalized.parts) >= 3 and normalized.parts[0] == UPLOAD_SOURCE_PREFIX:
        tool_name = normalized.parts[1]
        base_dir = get_tool_upload_dir(tool_name).resolve()
        safe_parts = [part for part in normalized.parts[2:] if part not in {"", ".", ".."}]
        candidate = base_dir.joinpath(*safe_parts) if safe_parts else base_dir
        try:
            resolved_candidate = candidate.resolve()
            resolved_candidate.relative_to(base_dir)
            return resolved_candidate
        except (OSError, ValueError):
            fallback_name = Path(str(source_name)).name
            return base_dir / fallback_name
    return settings.UPLOAD_DIR / Path(str(source_name)).name


def get_upload_tool_options() -> list[dict[str, str]]:
    return [
        {
            "name": tool_name,
            "label": str(RAG_TOOL_PROFILES[tool_name]["label"]),
            "description": str(RAG_TOOL_PROFILES[tool_name]["description"]),
        }
        for tool_name in RAG_TOOL_ORDER
    ]


def detect_tool_from_path(path: Path) -> Optional[str]:
    try:
        resolved_path = path.resolve()
    except OSError:
        resolved_path = path

    for tool_name in RAG_TOOL_ORDER:
        for root in get_tool_profile(tool_name).get("corpus_paths", []):
            root_path = Path(root)
            try:
                resolved_root = root_path.resolve()
            except OSError:
                resolved_root = root_path

            try:
                resolved_path.relative_to(resolved_root)
                return tool_name
            except ValueError:
                continue
    return None


__all__ = [
    "QA_ROOT",
    "RAG_UPLOAD_ROOT",
    "UPLOAD_SOURCE_PREFIX",
    "RAG_TOOL_PROFILES",
    "RAG_TOOL_ORDER",
    "DEFAULT_RAG_TOOL",
    "FALLBACK_RAG_NODE",
    "build_upload_source_name",
    "detect_tool_from_path",
    "get_tool_corpus_paths",
    "get_tool_profile",
    "get_tool_upload_dir",
    "get_upload_tool_options",
    "is_valid_rag_tool",
    "resolve_upload_source_path",
]
