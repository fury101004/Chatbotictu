
# vector_store.py – Vector Store với ChromaDB + Hybrid Search
# Mục đích: Retrieval cực nhanh, chính xác, ổn định cho chatbot nội bộ
#tiktoken + chromadb + rank_bm25 + sentence-transformers
#   • Hybrid = Vector (all-MiniLM-L6-v2) + BM25 (keyword)
#   • Bot-rule luôn top 1 (bất tử)
#   • Chunk thông minh theo heading + bảo vệ code/table
#   • Session memory per user (multi-turn conversation)
#   • Hybrid score chuẩn hóa + điều chỉnh trọng số
#   • Logging + thống kê chi tiết
""" luồng xử lý Data Ingestion & Chunking:
File upload → đọc nội dung.

Nếu file đã có → xóa chunk cũ.

Chia file thành chunks thông minh.

Tạo embeddings → lưu vào ChromaDB.

Thêm chunk BOT_RULE nếu cần.

Rebuild BM25 để hybrid search sẵn sàng.

Lưu file và metadata vào SQLite (botconfig.db)."""
import chromadb
from chromadb.utils import embedding_functions
import os
from pathlib import Path
from rank_bm25 import BM25Okapi
from typing import List, Tuple, Dict, Any, Optional
import re
import socket
import time
from functools import lru_cache
from datetime import datetime
from collections import defaultdict

from config.settings import settings
from pipelines.chunking_pipeline import (
    extract_academic_year as extract_academic_year_from_content,
    infer_document_type as infer_document_type_from_content,
    smart_chunk as build_smart_chunks,
)
from pipelines.embedding_pipeline import (
    build_embedding_function as build_embedding_function_from_pipeline,
    embedding_backend_ready as embedding_backend_ready_from_pipeline,
)
from pipelines.indexing_pipeline import index_document
from pipelines.vector_query_pipeline import (
    normalize_bm25_text as normalize_bm25_text_from_pipeline,
    normalize_scores as normalize_scores_from_pipeline,
    rebuild_bm25_index,
    run_hybrid_query,
    tokenize_bm25_text as tokenize_bm25_text_from_pipeline,
)
from shared.token_utils import count_text_tokens
from services.chat.memory_service import SESSION_MEMORY, clear_memory_store

# Metadata (title, level, source, word_count) được dùng để cho biết chunk đến từ đâu, thuộc phần nào, quan trọng cỡ nào và hiển thị preview

# Vector embeddings chỉ được load khi thật sự cần để app vẫn có thể boot offline.
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
ef = None
COLLECTION_NAME = "markdown_docs_v2"
COLLECTION_METADATA = {"hnsw:space": "cosine"}

# Chroma client cũng được khởi tạo lazy để tránh side effects lúc import module.
client = None

# Đường dẫn file nội quy bot
BOT_RULE_PATH = Path(settings.BOT_RULE_PATH)
BOT_RULE_ID = "BOT_RULE_001"                     # ID cố định để dễ tìm và ép lên đầu
BOT_RULE_FULL = ""                               # Bản đầy đủ (dùng khi context còn dư token)
BOT_RULE_SHORT = "# Quy tắc bot\nTrả lời ngắn gọn, tiếng Việt, chính xác, không thêm thắt."

# Memory ngắn hạn cho từng user → hỗ trợ hỏi follow-up thì bot nhớ
# user_id → deque(maxlen=6) tức nhớ tối đa 3 lượt hỏi-đáp (6 tin nhắn)
# Thống kê hiệu năng để sau này làm dashboard
STATS = {
    "total_queries": 0,
    "cache_hits": 0,
    "avg_time": 0.0,
    "start_time": time.time(),
    "popular_files": defaultdict(int)  # file nào được retrieve nhiều nhất
}

# 0.1 Load nội quy bot từ file (nếu chưa có thì tạo default)
def _load_bot_rule():
    """Đọc bot-rule.md, nếu chưa có thì tạo file với nội dung mặc định"""
    global BOT_RULE_FULL
    if BOT_RULE_PATH.exists():
        BOT_RULE_FULL = BOT_RULE_PATH.read_text(encoding="utf-8").strip()
        print("bot-rule.md loaded from file")
    else:
        BOT_RULE_FULL = "# Nội quy Bot\nBạn là trợ lý AI chuyên nghiệp, thân thiện và cực kỳ chính xác.\nTrả lời ngắn gọn, dùng tiếng Việt, không ba hoa, không thêm thắt thông tin ngoài tài liệu."
        BOT_RULE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BOT_RULE_PATH.write_text(BOT_RULE_FULL, encoding="utf-8")
        print("Created default bot-rule.md")


def get_bot_rule_text() -> str:
    if not BOT_RULE_FULL:
        _load_bot_rule()
    return BOT_RULE_FULL


def get_client():
    global client
    if client is None:
        client = chromadb.PersistentClient(path=str(settings.VECTORSTORE_DIR))
    return client


def count_tokens(text: str) -> int:
    return count_text_tokens(text)


def get_embedding_function():
    global ef
    if ef is None:
        ef = build_embedding_function_from_pipeline(
            current_embedding_function=ef,
            resolve_local_model_path=_resolve_local_embedding_model_path,
            embedding_factory=embedding_functions.SentenceTransformerEmbeddingFunction,
            model_name=EMBEDDING_MODEL_NAME,
        )
    return ef


def _local_embedding_model_candidates() -> list[Path]:
    model_slug = EMBEDDING_MODEL_NAME.replace("/", "--")
    home = Path.home()
    candidates = [
        home / ".cache" / "huggingface" / "hub" / f"models--sentence-transformers--{model_slug}",
        home / ".cache" / "torch" / "sentence_transformers" / EMBEDDING_MODEL_NAME,
    ]
    hf_home = os.getenv("HF_HOME", "").strip()
    if hf_home:
        candidates.append(Path(hf_home) / "hub" / f"models--sentence-transformers--{model_slug}")
    return candidates


def _has_complete_local_embedding_cache(candidate: Path) -> bool:
    if not candidate.exists():
        return False

    has_config = any(candidate.rglob("config.json"))
    has_tokenizer = any(candidate.rglob("tokenizer.json")) or any(candidate.rglob("tokenizer_config.json"))
    return has_config and has_tokenizer


def _resolve_local_embedding_model_path() -> Optional[Path]:
    for candidate in _local_embedding_model_candidates():
        if not _has_complete_local_embedding_cache(candidate):
            continue

        modules = list(candidate.rglob("modules.json"))
        if modules:
            return modules[0].parent
        return candidate
    return None


def embedding_backend_ready() -> bool:
    return embedding_backend_ready_from_pipeline(
        resolve_local_model_path=_resolve_local_embedding_model_path,
        network_host="huggingface.co",
        network_port=443,
        timeout=0.75,
    )


def _clear_embedding_backend_ready_cache() -> None:
    return None


embedding_backend_ready.cache_clear = _clear_embedding_backend_ready_cache


_load_bot_rule()

# 1. CHROMA COLLECTION – Nơi chứa tất cả chunk + embedding
def get_collection():
    """
    Tạo hoặc lấy collection tên markdown_docs_v2
    Dùng cosine distance (phù hợp với sentence transformer)
    """
    return get_client().get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=get_embedding_function(),
        metadata=COLLECTION_METADATA  # HNSW index dùng cosine
    )


def get_collection_readonly():
    """Read vector metadata/documents without loading the embedding backend."""
    try:
        return get_client().get_collection(name=COLLECTION_NAME)
    except Exception:
        return get_client().get_or_create_collection(
            name=COLLECTION_NAME,
            metadata=COLLECTION_METADATA,
        )

# 2. BM25 – Keyword search siêu nhanh (lazy rebuild)
_bm25: Optional[BM25Okapi] = None
_all_tokenized: List[List[str]] = []   # danh sách các doc đã tokenize để BM25 dùng
_all_ids: List[str] = []               # mapping vị trí → chroma id
_last_count = -1                       # để biết DB có thay đổi không → rebuild BM25


def _normalize_bm25_text(text: str) -> str:
    return normalize_bm25_text_from_pipeline(text)


def _tokenize_bm25_text(text: str) -> list[str]:
    return tokenize_bm25_text_from_pipeline(text)


# b6 Tokenize tất cả document.Tạo BM25 index để hỗ trợ hybrid search (vector + BM25).
def _rebuild_bm25():
    """Chỉ rebuild BM25 khi số lượng document thay đổi → cực nhẹ RAM/CPU"""
    global _bm25, _all_tokenized, _all_ids, _last_count
    _bm25, _all_tokenized, _all_ids, _last_count = rebuild_bm25_index(
        collection_getter=get_collection,
        current_bm25=_bm25,
        current_tokenized=_all_tokenized,
        current_ids=_all_ids,
        current_count=_last_count,
        bm25_factory=BM25Okapi,
        tokenize_text_fn=_tokenize_bm25_text,
    )


def _normalize_scores(raw_scores: Dict[str, float]) -> Dict[str, float]:
    return normalize_scores_from_pipeline(raw_scores)


def _top_bm25_candidates(query: str, limit: int) -> tuple[Dict[str, float], list[str]]:
    from pipelines.vector_query_pipeline import top_bm25_candidates

    return top_bm25_candidates(
        query,
        bm25_index=_bm25,
        all_ids=_all_ids,
        limit=limit,
        tokenize_text_fn=_tokenize_bm25_text,
    )

# 3. SMART CHUNKING – delegated to ingestion pipeline
def _extract_academic_year(source_name: str, filename: str, content: str) -> Optional[str]:
    return extract_academic_year_from_content(source_name, filename, content)


def _infer_document_type(source_name: str, filename: str, tool_name: Optional[str], content: str) -> str:
    return infer_document_type_from_content(source_name, filename, tool_name, content)


def smart_chunk(content: str, filename: str, source_name: Optional[str] = None) -> List[Dict[str, Any]]:
    return build_smart_chunks(
        content,
        filename,
        source_name=source_name,
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        count_tokens_fn=count_tokens,
    )

def add_documents(
    file_content: str,
    filename: str,
    version: str = "latest",
    source_name: Optional[str] = None,
    tool_name: Optional[str] = None,
) -> None:
    """
    Thêm hoặc cập nhật một file markdown vào vector store
    - Xóa hết chunk cũ của file đó trước
    - Chunk thông minh
    - Add từng batch nhỏ để tránh treo khi file siêu to
    """
    index_document(
        file_content=file_content,
        filename=filename,
        version=version,
        source_name=source_name,
        tool_name=tool_name,
        collection_getter=get_collection,
        smart_chunk_fn=smart_chunk,
        extract_academic_year_fn=_extract_academic_year,
        infer_document_type_fn=_infer_document_type,
        rebuild_bm25_fn=_rebuild_bm25,
        inject_bot_rule_fn=inject_bot_rule,
    )


# b5. INJECT BOT RULE dựa vào file bot-rule.md để Đảm bảo khi LLM lấy context, rule luôn được ưu tiên 
def inject_bot_rule(force_full: bool = False):
    """
    Chèn/cập nhật nội quy bot vào Chroma
    - force_full=True → dùng bản dài (dùng khi context còn rộng)
    - Mặc định dùng bản ngắn để tiết kiệm token
    """
    try:
        coll = get_collection()
    except Exception as exc:
        print(f"Bỏ qua inject_bot_rule vì vector store chưa sẵn sàng: {exc}")
        return

    rule_text = get_bot_rule_text() if force_full else BOT_RULE_SHORT
    coll.upsert(
        ids=[BOT_RULE_ID],
        documents=[rule_text],
        metadatas=[{
            "source": "BOT_RULE",
            "title": "Nội quy & giọng điệu bot",
            "priority": 999999,
            "is_rule": True,
            "created_at": datetime.now().isoformat()
        }]
    )

# 6. HYBRID SEARCH dùng để truy vấn tài liệu với hybrid search (vector + BM25) và ép bot-rule lên đầu.
def query_documents(
    query: str,
    user_id: str = "default",
    n_results: int = 8,
    alpha: float = 0.75  # 0.0 = chỉ BM25, 1.0 = chỉ vector. 0.75 thường ngon nhất
) -> Tuple[List[str], List[dict], Dict]:
    """
    Hybrid search + ép bot-rule lên đầu + lưu session
    Trả về:
        docs, metas, extra_info (session, stats, sources)
    """
    coll = get_collection()
    _rebuild_bm25()  # đảm bảo BM25 mới nhất
    return run_hybrid_query(
        collection=coll,
        query=query,
        user_id=user_id,
        n_results=n_results,
        alpha=alpha,
        bm25_index=_bm25,
        all_ids=_all_ids,
        tokenize_text_fn=_tokenize_bm25_text,
        bot_rule_id=BOT_RULE_ID,
        session_memory=SESSION_MEMORY,
        stats=STATS,
    )

# 7. HỖ TRỢ & RESET VECTOR STORE 

def reset_vectorstore():
    """Xóa sạch dữ liệu – dùng khi reload toàn bộ tài liệu"""
    get_client().delete_collection("markdown_docs_v2")
    global _bm25, _last_count, _all_ids, _all_tokenized
    _bm25 = None
    _all_ids = []
    _all_tokenized = []
    _last_count = -1
    clear_memory_store()
    STATS["popular_files"].clear()
    STATS["total_queries"] = 0
    print("Da reset toan bo vector store!")
    inject_bot_rule()          # rule vẫn sống sau reset
# 8. LẤY THỐNG KÊ
def get_stats():
    """Lấy thống kê để hiển thị dashboard"""
    uptime = time.time() - STATS["start_time"]
    return {
        **STATS,
        "uptime_hours": round(uptime / 3600, 2),
        "qps": round(STATS["total_queries"] / max(uptime, 1), 2)
    }

# KHỞI TẠO AN TOÀN KHI CẦN
def initialize_vectorstore():
    coll = get_collection()
    # Đảm bảo load bot rule
    inject_bot_rule()
    print("Bot-rule đã được inject - luôn dùng top 1")
    if coll.count() > 0:
        _rebuild_bm25()
        print(f"Warm-up BM25 thành công với {coll.count()} chunks")
    else:
        print("Vector store hiện đang trống - chờ add tài liệu đầu tiên")
    print("="*70)
    print("VECTOR STORE v2.0 ĐÃ KHỞI ĐỘNG HOÀN TOÀN")
    print("- Hybrid search đã chuẩn hóa - Bot-rule bất tử - Session memory - Logging")
    print("- Tốc độ ~1.0-1.8s/query - RAM nhẹ - Enterprise ready")
    print("="*70)

