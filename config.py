import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency at runtime
    load_dotenv = None


if load_dotenv is not None:
    load_dotenv()


# ==== ĐƯỜNG DẪN GỐC DỰ ÁN ====
ROOT_DIR = Path(__file__).resolve().parent


# ==== CẤU HÌNH FLASK / BẢO MẬT ====
SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "1") == "1"
FLASK_USE_RELOADER = os.getenv("FLASK_USE_RELOADER", "0") == "1"


# ==== CẤU HÌNH CSDL LỊCH SỬ CHAT ====
DB_NAME = os.getenv("CHAT_DB_NAME", str(ROOT_DIR / "chat.db"))


# ==== CẤU HÌNH DỮ LIỆU RAG ====
# Thư mục dữ liệu gốc (pdf/docx) trước khi làm sạch
RAW_DATA_DIR = Path(os.getenv("RAW_DATA_DIR", str(ROOT_DIR / "datadoan")))

# Thư mục chứa markdown đã làm sạch cho RAG
CLEAN_MD_DIR = Path(os.getenv("CLEAN_MD_DIR", str(ROOT_DIR / "clean_md")))

# Thư mục markdown tối ưu cho chunk/RAG (tạo từ clean_md)
RAG_MD_DIR = Path(os.getenv("RAG_MD_DIR", str(ROOT_DIR / "rag_md")))

# Thư mục dữ liệu txt (nếu có) cho RAG
TXT_DATA_DIR = Path(os.getenv("TXT_DATA_DIR", str(ROOT_DIR / "data")))

# Thư mục lưu FAISS vector DB
VECTOR_DB_DIR = Path(os.getenv("VECTOR_DB_DIR", str(ROOT_DIR / "vector_db")))


# ==== CẤU HÌNH MÔ HÌNH NGÔN NGỮ (OLLAMA) ====
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")


# ==== CẤU HÌNH EMBEDDINGS ====
EMBEDDINGS_MODEL = os.getenv(
    "EMBEDDINGS_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)


# ==== CAU HINH RERANKER ====
# Mac dinh tat neural reranker de tranh loi torch/DLL tren Windows.
ENABLE_NEURAL_RERANKER = os.getenv("ENABLE_NEURAL_RERANKER", "0") == "1"
NEURAL_RERANKER_MODEL = os.getenv(
    "NEURAL_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
)

