import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
APP_DIR = ROOT_DIR / "app"
TEMPLATES_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency at runtime
    load_dotenv = None


if load_dotenv is not None:
    load_dotenv(ROOT_DIR / ".env")


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int, *, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        value = default
    else:
        try:
            value = int(raw.strip())
        except ValueError as exc:
            raise RuntimeError(f"{name} phải là số nguyên hợp lệ.") from exc

    if minimum is not None and value < minimum:
        raise RuntimeError(f"{name} phải lớn hơn hoặc bằng {minimum}.")

    return value


APP_NAME = os.getenv("APP_NAME", "ICTU Student Assistant")
APP_DESCRIPTION = os.getenv(
    "APP_DESCRIPTION",
    "Chatbot tra cứu học vụ, văn bản và kho tri thức sinh viên ICTU.",
)
APP_ENV = (os.getenv("APP_ENV", "development") or "development").strip().lower()
APP_DEBUG = _get_bool("APP_DEBUG", True)
IS_PRODUCTION = APP_ENV == "production"

_raw_secret = (os.getenv("SECRET_KEY") or "").strip()
if _raw_secret:
    SECRET_KEY = _raw_secret
elif IS_PRODUCTION:
    raise RuntimeError("SECRET_KEY is required when APP_ENV=production.")
else:
    SECRET_KEY = "dev-secret-key"

if IS_PRODUCTION and SECRET_KEY == "dev-secret-key":
    raise RuntimeError("SECRET_KEY must not use the development default in production.")

SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "ictu_session")
SESSION_SAME_SITE = (os.getenv("SESSION_SAME_SITE", "lax") or "lax").strip().lower()
if SESSION_SAME_SITE not in {"lax", "strict", "none"}:
    raise RuntimeError("SESSION_SAME_SITE phải là 'lax', 'strict' hoặc 'none'.")
SESSION_HTTPS_ONLY = _get_bool("SESSION_HTTPS_ONLY", IS_PRODUCTION)

SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
SERVER_PORT = _get_int("SERVER_PORT", 5000, minimum=1)
UVICORN_RELOAD = _get_bool("UVICORN_RELOAD", False)

DB_NAME = Path(os.getenv("CHAT_DB_NAME", str(ROOT_DIR / "chat.db")))

RAW_DATA_DIR = Path(os.getenv("RAW_DATA_DIR", str(ROOT_DIR / "datadoan")))
CLEAN_MD_DIR = Path(os.getenv("CLEAN_MD_DIR", str(ROOT_DIR / "clean_md")))
RAG_MD_DIR = Path(os.getenv("RAG_MD_DIR", str(ROOT_DIR / "rag_md")))
TXT_DATA_DIR = Path(os.getenv("TXT_DATA_DIR", str(ROOT_DIR / "data")))
VECTOR_DB_DIR = Path(os.getenv("VECTOR_DB_DIR", str(ROOT_DIR / "vector_db")))

UPLOADS_DIR_NAME = os.getenv("UPLOADS_DIR_NAME", "_uploads")
MAX_UPLOAD_SIZE_MB = _get_int("MAX_UPLOAD_SIZE_MB", 25, minimum=1)

LLM_PROVIDER = (os.getenv("LLM_PROVIDER", "ollama") or "ollama").strip().lower()
SUPPORTED_LLM_PROVIDERS = {"ollama", "gemini", "auto"}

if LLM_PROVIDER not in SUPPORTED_LLM_PROVIDERS:
    raise RuntimeError("LLM_PROVIDER phải là 'ollama', 'gemini' hoặc 'auto'.")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")


def resolve_llm_provider(provider: str | None = None) -> str:
    selected = (provider or LLM_PROVIDER or "ollama").strip().lower()
    if selected not in SUPPORTED_LLM_PROVIDERS:
        raise RuntimeError("LLM_PROVIDER phải là 'ollama', 'gemini' hoặc 'auto'.")

    if selected == "auto":
        return "gemini" if GEMINI_API_KEY else "ollama"

    return selected


ACTIVE_LLM_PROVIDER = resolve_llm_provider()
ACTIVE_LLM_MODEL = GEMINI_MODEL if ACTIVE_LLM_PROVIDER == "gemini" else OLLAMA_MODEL

EMBEDDINGS_MODEL = os.getenv(
    "EMBEDDINGS_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)

ENABLE_NEURAL_RERANKER = _get_bool("ENABLE_NEURAL_RERANKER", False)
NEURAL_RERANKER_MODEL = os.getenv(
    "NEURAL_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
)
