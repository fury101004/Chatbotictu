
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
import hashlib
import re
import socket
import time
import json
from functools import lru_cache
from datetime import datetime
from collections import defaultdict, deque
import unicodedata

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
from shared.token_utils import count_text_tokens
from services.memory_service import SESSION_MEMORY, clear_memory_store

# Metadata (title, level, source, word_count) được dùng để cho biết chunk đến từ đâu, thuộc phần nào, quan trọng cỡ nào và hiển thị preview

# Vector embeddings chỉ được load khi thật sự cần để app vẫn có thể boot offline.
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
ef = None

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
        name="markdown_docs_v2",
        embedding_function=get_embedding_function(),
        metadata={"hnsw:space": "cosine"}  # HNSW index dùng cosine
    )

# 2. BM25 – Keyword search siêu nhanh (lazy rebuild)
_bm25: Optional[BM25Okapi] = None
_all_tokenized: List[List[str]] = []   # danh sách các doc đã tokenize để BM25 dùng
_all_ids: List[str] = []               # mapping vị trí → chroma id
_last_count = -1                       # để biết DB có thay đổi không → rebuild BM25


def _normalize_bm25_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or "").casefold())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.replace("đ", "d").replace("&", " va ")
    return re.sub(r"\s+", " ", normalized).strip()


def _tokenize_bm25_text(text: str) -> list[str]:
    normalized = _normalize_bm25_text(text)
    return [token for token in re.findall(r"[a-z0-9]+", normalized) if len(token) > 1]


# b6 Tokenize tất cả document.Tạo BM25 index để hỗ trợ hybrid search (vector + BM25).
def _rebuild_bm25():
    """Chỉ rebuild BM25 khi số lượng document thay đổi → cực nhẹ RAM/CPU"""
    global _bm25, _all_tokenized, _all_ids, _last_count
    coll = get_collection()
    current = coll.count()

    # Nếu số lượng không đổi và đã có BM25 rồi → bỏ qua
    if current == _last_count and _bm25 is not None:
        return

    # Lấy toàn bộ document + id từ Chroma
    data = coll.get(include=["documents"])
    docs = data["documents"]
    ids = data["ids"]

    # Tokenize đơn giản (lower + split) để BM25 dùng
    _all_tokenized = [_tokenize_bm25_text(doc) for doc in docs]
    _all_ids = ids
    _bm25 = BM25Okapi(_all_tokenized) if docs else None
    _last_count = current
    print(f"BM25 rebuilt with {len(docs)} chunks")


def _normalize_scores(raw_scores: Dict[str, float]) -> Dict[str, float]:
    if not raw_scores:
        return {}
    minimum = min(raw_scores.values())
    maximum = max(raw_scores.values())
    if maximum <= minimum:
        return {key: 1.0 for key in raw_scores}
    return {
        key: (value - minimum) / (maximum - minimum + 1e-8)
        for key, value in raw_scores.items()
    }


def _top_bm25_candidates(query: str, limit: int) -> tuple[Dict[str, float], list[str]]:
    if _bm25 is None or not _all_ids:
        return {}, []

    query_tokens = _tokenize_bm25_text(query)
    if not query_tokens:
        return {}, []

    bm25_raw = _bm25.get_scores(query_tokens)
    raw_scores = {doc_id: float(bm25_raw[index]) for index, doc_id in enumerate(_all_ids)}
    ranked_ids = [
        doc_id
        for doc_id, score in sorted(raw_scores.items(), key=lambda item: item[1], reverse=True)
        if score > 0
    ][:limit]
    return _normalize_scores(raw_scores), ranked_ids

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

# 4. ADD DOCUMENTS – Xóa cũ, thêm mới, tự động chunk
def _build_chunk_id_prefix(source_name: str) -> str:
    digest = hashlib.sha1(source_name.encode("utf-8", errors="ignore")).hexdigest()[:12]
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", source_name).strip("_") or "document"
    return f"{safe_name}__{digest}"


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
@lru_cache(maxsize=500)
def _cached_embedding(query: str):
    """Cache embedding của query → vector search nhanh hơn rất nhiều"""
    return get_embedding_function()([query])[0]
# b4 Truy vấn tài liệu với hybrid search (vector + BM25) và ép bot-rule lên đầu.
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
    start = time.time()
    STATS["total_queries"] += 1

    coll = get_collection()
    _rebuild_bm25()  # đảm bảo BM25 mới nhất
    if coll.count() == 0:
        return [], [], {"session_history": list(SESSION_MEMORY[user_id]), "stats": STATS.copy(), "sources": []}

    vector_candidate_limit = max(n_results + 15, n_results * 3)
    bm25_candidate_limit = max(n_results + 10, n_results * 2)

    # vector search đầu tiên để lấy candidates
    vec = coll.query(
        query_texts=[query],
        n_results=vector_candidate_limit,
        include=["documents", "metadatas", "distances"]
    )

    v_ids = vec["ids"][0]
    v_distances = vec["distances"][0]   # cosine distance: 0 = giống, 2 = khác

    # Chuyển distance → similarity (0-1)
    cosine_raw = {
        doc_id: 1.0 - distance
        for doc_id, distance in zip(v_ids, v_distances)
    }
    norm_cosine = _normalize_scores(cosine_raw)
    norm_bm25, bm25_ids = _top_bm25_candidates(query, bm25_candidate_limit)

    candidate_ids = list(dict.fromkeys([*v_ids, *bm25_ids]))
    if BOT_RULE_ID not in candidate_ids:
        candidate_ids.append(BOT_RULE_ID)

    # hybrid_scores dùng để kết hợp 2 điểm số
    hybrid_scores: Dict[str, float] = {}
    for doc_id in candidate_ids:
        c_score = norm_cosine.get(doc_id, 0.0)
        b_score = norm_bm25.get(doc_id, 0.0)
        hybrid_scores[doc_id] = alpha * c_score + (1 - alpha) * b_score
        if doc_id == BOT_RULE_ID:
            hybrid_scores[doc_id] = 2.0

    # Lấy top candidates
    ranked_ids = [
        doc_id
        for doc_id, _score in sorted(hybrid_scores.items(), key=lambda item: item[1], reverse=True)
    ]
    top_ids = ranked_ids[: n_results + 5]

    # Lấy nội dung thật
    results = coll.get(ids=top_ids, include=["documents", "metadatas"])
    docs = results["documents"]
    metas = results["metadatas"]
    ids = results["ids"]
    items_by_id = {
        doc_id: (document, metadata)
        for doc_id, document, metadata in zip(ids, docs, metas)
    }

    # cho bot rule luôn đứng đầu
    rule_doc = None
    rule_meta = None
    normal_docs = []
    normal_metas = []

    for doc_id in top_ids:
        item = items_by_id.get(doc_id)
        if item is None:
            continue
        d, m = item
        if m.get("source") == "BOT_RULE" or doc_id == BOT_RULE_ID:
            rule_doc = d
            rule_meta = m
        else:
            enriched_meta = dict(m or {})
            enriched_meta["hybrid_score"] = round(hybrid_scores.get(doc_id, 0.0), 6)
            enriched_meta["vector_score"] = round(norm_cosine.get(doc_id, 0.0), 6)
            enriched_meta["bm25_score"] = round(norm_bm25.get(doc_id, 0.0), 6)
            normal_docs.append(d)
            normal_metas.append(enriched_meta)

    # Nếu rule không có trong top → lấy thủ công
    if not rule_doc:
        rule_data = coll.get(ids=[BOT_RULE_ID], include=["documents", "metadatas"])
        if rule_data["documents"]:
            rule_doc = rule_data["documents"][0]
            rule_meta = rule_data["metadatas"][0]

    # Ghép lại: rule luôn top 1
    final_docs = []
    final_metas = []
    if rule_doc:
        final_docs.append(rule_doc)
        final_metas.append(rule_meta)

    final_docs.extend(normal_docs[:n_results - 1])
    final_metas.extend(normal_metas[:n_results - 1])

    #lưu session memory cho user
    SESSION_MEMORY[user_id].append({
        "query": query,
        "timestamp": datetime.now().isoformat(),
        "sources": [m.get("source", "") for m in final_metas if m.get("source") != "BOT_RULE"],
        "retrieved_ids": ranked_ids[:n_results]
    })

    # Cập nhật thống kê
    elapsed = time.time() - start
    STATS["avg_time"] = (STATS["avg_time"] * (STATS["total_queries"] - 1) + elapsed) / STATS["total_queries"]
    for m in final_metas:
        if m.get("source") not in ["BOT_RULE", None]:
            STATS["popular_files"][m["source"]] += 1

    print(f"QUERY OK | {elapsed:.3f}s | alpha={alpha} | {len(final_docs)} results | User: {user_id[-8:]}")

    return final_docs, final_metas, {
        "session_history": list(SESSION_MEMORY[user_id]),
        "stats": STATS.copy(),
        "sources": list(set(m.get("source") for m in final_metas if m.get("source") != "BOT_RULE"))
    }

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
