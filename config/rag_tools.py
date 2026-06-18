from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Optional

from config.settings import settings


QA_ROOT = Path(settings.QA_CORPUS_ROOT)
RAG_UPLOAD_ROOT = Path(settings.RAG_UPLOAD_ROOT)
UPLOAD_SOURCE_PREFIX = "uploads"

RAG_TOOL_CORPUS_DIRS = {
    "student_handbook_rag": QA_ROOT / "student_handbooks",
    "academic_policy_rag": QA_ROOT / "academic_policies",
    "student_faq_rag": QA_ROOT / "student_faqs",
    "general_ictu_rag": QA_ROOT / "general_ictu",
}

RAG_TOOL_PROFILES = {
    "student_handbook_rag": {
        "label": "Sổ tay sinh viên",
        "description": (
            "Sổ tay, cẩm nang tân sinh viên, thông tin tổng quan theo khóa, "
            "chương trình đào tạo, điều kiện xét/công nhận tốt nghiệp theo năm học "
            "và các quy định dành cho người học."
        ),
        "corpus_paths": [
            RAG_TOOL_CORPUS_DIRS["student_handbook_rag"],
        ],
        "metadata_filter": {"tool_name": "student_handbook_rag"},
        "route_keywords": [
            "sổ tay",
            "cẩm nang",
            "handbook",
            "tân sinh viên",
            "người học",
            "hành vi",
            "không được làm",
            "danh hiệu sinh viên",
            "khá giỏi xuất sắc",
            "chương trình học",
            "chương trình đào tạo",
            "ctdt",
            "tín chỉ",
            "học lại",
            "đăng ký học lại",
            "học cải thiện",
            "cải thiện điểm",
            "điểm học phần",
            "bảo lưu",
            "bảo lưu kết quả học tập",
            "nghỉ học tạm thời",
            "điều kiện tốt nghiệp",
            "xét tốt nghiệp",
            "công nhận tốt nghiệp",
            "khóa 20",
            "khóa 21",
            "khóa 22",
            "khóa 23",
            "khóa 24",
            "k20",
            "k21",
            "k22",
            "k23",
            "k24",
        ],
    },
    "academic_policy_rag": {
        "label": "Quy định và chính sách",
        "description": (
            "Quy chế, quy định, quyết định, thông tư, học phí, học bổng, "
            "điểm rèn luyện và các chế độ chính sách."
        ),
        "corpus_paths": [
            RAG_TOOL_CORPUS_DIRS["academic_policy_rag"],
        ],
        "metadata_filter": {"tool_name": "academic_policy_rag"},
        "route_keywords": [
            "quy chế",
            "quy định",
            "quyết định",
            "thông tư",
            "nghị định",
            "luật",
            "chính sách",
            "miễn giảm",
            "mghp",
            "trợ cấp",
            "học bổng",
            "học phí",
            "điểm rèn luyện",
            "đrl",
            "drl",
            "kỷ luật",
            "khen thưởng",
        ],
    },
    "student_faq_rag": {
        "label": "FAQ sinh viên",
        "description": (
            "Câu hỏi thường gặp về quy trình, email, hồ sơ, thủ tục tốt nghiệp, việc làm, "
            "bảo hiểm, đăng ký học và hỏi đáp tác vụ."
        ),
        "corpus_paths": [
            RAG_TOOL_CORPUS_DIRS["student_faq_rag"],
        ],
        "metadata_filter": {"tool_name": "student_faq_rag"},
        "route_keywords": [
            "khi nào",
            "bao giờ",
            "ở đâu",
            "làm sao",
            "thế nào",
            "email",
            "tốt nghiệp",
            "xét tốt nghiệp",
            "việc làm",
            "tuyển dụng",
            "hồ sơ",
            "bảo hiểm",
            "bhyt",
            "đăng ký",
        ],
    },
    "general_ictu_rag": {
        "label": "Thông tin chung ICTU",
        "description": (
            "Thông tin tổng quan về ICTU, tuyển sinh, ngành đào tạo, điểm chuẩn, "
            "địa chỉ, liên hệ, tin tức và sự kiện."
        ),
        "corpus_paths": [
            RAG_TOOL_CORPUS_DIRS["general_ictu_rag"],
        ],
        "metadata_filter": {"tool_name": "general_ictu_rag"},
        "route_keywords": [
            "ictu",
            "tuyển sinh",
            "ngành đào tạo",
            "điểm chuẩn",
            "địa chỉ",
            "liên hệ",
            "giới thiệu",
            "tin tức",
            "sự kiện",
            "website",
        ],
    },
}

RAG_TOOL_ORDER = [
    "student_handbook_rag",
    "academic_policy_rag",
    "student_faq_rag",
    "general_ictu_rag",
]
DEFAULT_RAG_TOOL = "general_ictu_rag"
FALLBACK_RAG_NODE = "general_ictu_rag"


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _validate_corpus_ownership() -> None:
    resolved_qa_root = QA_ROOT.resolve()
    roots_by_tool: dict[str, list[Path]] = {}

    for tool_name, profile in RAG_TOOL_PROFILES.items():
        roots = [Path(path).resolve() for path in profile.get("corpus_paths", [])]
        if any(root == resolved_qa_root for root in roots):
            raise ValueError(f"{tool_name} must not use the shared QA_ROOT as its corpus source")
        if profile.get("metadata_filter") != {"tool_name": tool_name}:
            raise ValueError(f"{tool_name} must use its own tool_name metadata filter")
        roots_by_tool[tool_name] = roots

    for index, tool_name in enumerate(RAG_TOOL_ORDER):
        for other_tool_name in RAG_TOOL_ORDER[index + 1 :]:
            for root in roots_by_tool[tool_name]:
                for other_root in roots_by_tool[other_tool_name]:
                    if _path_is_within(root, other_root) or _path_is_within(other_root, root):
                        raise ValueError(
                            f"Corpus sources overlap between {tool_name} and {other_tool_name}: "
                            f"{root} / {other_root}"
                        )


_validate_corpus_ownership()


def is_valid_rag_tool(tool_name: Optional[str]) -> bool:
    return bool(tool_name) and tool_name in RAG_TOOL_PROFILES


def get_tool_profile(tool_name: Optional[str]) -> dict:
    if is_valid_rag_tool(tool_name):
        return RAG_TOOL_PROFILES[str(tool_name)]
    return RAG_TOOL_PROFILES[DEFAULT_RAG_TOOL]


def get_tool_metadata_filter(tool_name: Optional[str]) -> dict[str, str]:
    profile = get_tool_profile(tool_name)
    return dict(profile.get("metadata_filter", {}))


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
    "RAG_TOOL_CORPUS_DIRS",
    "RAG_TOOL_PROFILES",
    "RAG_TOOL_ORDER",
    "DEFAULT_RAG_TOOL",
    "FALLBACK_RAG_NODE",
    "build_upload_source_name",
    "detect_tool_from_path",
    "get_tool_corpus_paths",
    "get_tool_metadata_filter",
    "get_tool_profile",
    "get_tool_upload_dir",
    "get_upload_tool_options",
    "is_valid_rag_tool",
    "resolve_upload_source_path",
]
