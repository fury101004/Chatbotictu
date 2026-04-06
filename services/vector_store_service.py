
# vector_store.py – Vector Store với ChromaDB + Hybrid Search
# Mục đích: Retrieval cực nhanh, chính xác, ổn định cho chatbot nội bộ
#tiktoken + chromadb + rank_bm25 + sentence-transformers
#   • Hybrid = Vector (all-MiniLM-L6-v2) + BM25 (keyword)
#   • Bot-rule luôn top 1 (bất tử)
#   • Chunk thông minh theo heading + bảo vệ code/table
#   • Session memory per user (multi-turn conversation)
#   â€¢ Hybrid score chuáº©n hĂ³a + Ä‘iá»u chá»‰nh trá»ng sá»‘
#   • Logging + thống kê chi tiết
""" luồng xử lý Data Ingestion & Chunking:
File upload â†’ Ä‘á»c ná»™i dung.

Nếu file đã có → xóa chunk cũ.

Chia file thành chunks thông minh.

Tạo embeddings → lưu vào ChromaDB.

Thêm chunk BOT_RULE nếu cần.

Rebuild BM25 để hybrid search sẵn sàng.

Lưu file và metadata vào SQLite (botconfig.db)."""
import chromadb
from chromadb.utils import embedding_functions
from pathlib import Path
from rank_bm25 import BM25Okapi
from typing import List, Tuple, Dict, Any, Optional
import hashlib
import re
import time
import json
from functools import lru_cache
from datetime import datetime
from collections import defaultdict, deque
import tiktoken  

# Metadata (title, level, source, word_count) được dùng để cho biết chunk đến từ đâu, thuộc phần nào, quan trọng cỡ nào và hiển thị preview

# Vector embeddings chỉ được load khi thật sự cần để app vẫn có thể boot offline.
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
ef = None

# Chroma client cũng được khởi tạo lazy để tránh side effects lúc import module.
client = None

# DĂ¹ng Ä‘á»ƒ Ä‘áº¿m token (ráº¥t quan trá»ng khi chunk vĂ  tĂ­nh context length cho LLM)
encoding = tiktoken.get_encoding("cl100k_base")

# ÄÆ°á»ng dáº«n file ná»™i quy bot
BOT_RULE_PATH = Path("data/bot-rule.md")
BOT_RULE_ID = "BOT_RULE_001"                     # ID cố định để dễ tìm và ép lên đầu
BOT_RULE_FULL = ""                               # Bản đầy đủ (dùng khi context còn dư token)
BOT_RULE_SHORT = "# Quy táº¯c bot\nTráº£ lá»i ngáº¯n gá»n, tiáº¿ng Viá»‡t, chĂ­nh xĂ¡c, khĂ´ng thĂªm tháº¯t."

# Memory ngáº¯n háº¡n cho tá»«ng user â†’ há»— trá»£ há»i follow-up thĂ¬ bot nhá»›
# user_id â†’ deque(maxlen=6) tá»©c nhá»› tá»‘i Ä‘a 3 lÆ°á»£t há»i-Ä‘Ă¡p (6 tin nháº¯n)
SESSION_MEMORY: Dict[str, deque] = defaultdict(lambda: deque(maxlen=6))

# Thống kê hiệu năng để sau này làm dashboard
STATS = {
    "total_queries": 0,
    "cache_hits": 0,
    "avg_time": 0.0,
    "start_time": time.time(),
    "popular_files": defaultdict(int)  # file nĂ o Ä‘Æ°á»£c retrieve nhiá»u nháº¥t
}

# 0.1 Load nội quy bot từ file (nếu chưa có thì tạo default)
def _load_bot_rule():
    """Äá»c bot-rule.md, náº¿u chÆ°a cĂ³ thĂ¬ táº¡o file vá»›i ná»™i dung máº·c Ä‘á»‹nh"""
    global BOT_RULE_FULL
    if BOT_RULE_PATH.exists():
        BOT_RULE_FULL = BOT_RULE_PATH.read_text(encoding="utf-8").strip()
        print("bot-rule.md loaded from file")
    else:
        BOT_RULE_FULL = "# Ná»™i quy Bot\nBáº¡n lĂ  trá»£ lĂ½ AI chuyĂªn nghiá»‡p, thĂ¢n thiá»‡n vĂ  cá»±c ká»³ chĂ­nh xĂ¡c.\nTráº£ lá»i ngáº¯n gá»n, dĂ¹ng tiáº¿ng Viá»‡t, khĂ´ng ba hoa, khĂ´ng thĂªm tháº¯t thĂ´ng tin ngoĂ i tĂ i liá»‡u."
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
        client = chromadb.PersistentClient(path="./vectorstore")
    return client


def get_embedding_function():
    global ef
    if ef is None:
        print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL_NAME)
    return ef


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
# b6 Tokenize tất cả document.Tạo BM25 index để hỗ trợ hybrid search (vector + BM25).
def _rebuild_bm25():
    """Chỉ rebuild BM25 khi số lượng document thay đổi → cực nhẹ RAM/CPU"""
    global _bm25, _all_tokenized, _all_ids, _last_count
    coll = get_collection()
    current = coll.count()

    # Náº¿u sá»‘ lÆ°á»£ng khĂ´ng Ä‘á»•i vĂ  Ä‘Ă£ cĂ³ BM25 rá»“i â†’ bá» qua
    if current == _last_count and _bm25 is not None:
        return

    # Lấy toàn bộ document + id từ Chroma
    data = coll.get(include=["documents"])
    docs = data["documents"]
    ids = data["ids"]

    # Tokenize đơn giản (lower + split) để BM25 dùng
    _all_tokenized = [doc.lower().split() for doc in docs]
    _all_ids = ids
    _bm25 = BM25Okapi(_all_tokenized) if docs else None
    _last_count = current
    print(f"BM25 rebuilt with {len(docs)} chunks")

# 3. SMART CHUNKING â€“ Chia nhá» file thĂ nh cĂ¡c chunk thĂ´ng minh
def smart_chunk(content: str, filename: str) -> List[Dict[str, Any]]:
    """
    Chunk theo:
        • Heading (# ## ### ####)
        • Không cắt ngang code block (```)
        • Không vượt quá ~512 token (an toàn cho hầu hết LLM)
        • Phát hiện table để đánh dấu chunk_type
    """
    lines = content.split("\n")
    chunks = []
    buffer = []                # các dòng đang gom lại thành 1 chunk
    buffer_tokens = 0
    current_title = Path(filename).stem
    in_code_block = False

    def flush_buffer():
        """Äáº©y buffer hiá»‡n táº¡i thĂ nh 1 chunk hoĂ n chá»‰nh"""
        nonlocal buffer_tokens
        if not buffer:
            return
        text = "\n".join(buffer).strip()
        if not text:
            buffer.clear()
            return

        token_count = len(encoding.encode(text))

        # Phát hiện loại chunk để sau này LLM xử lý đặc biệt
        if in_code_block:
            chunk_type = "code"
        elif any(c in text for c in ["â”‚", "â”ƒ", "â”œ", "â”£", "â”³", "â•"]):  # báº£ng markdown thÆ°á»ng dĂ¹ng cĂ¡c kĂ½ tá»± nĂ y
            chunk_type = "table"
        elif bullet := re.search(r'^[-*•]\s', text, re.M):
            chunk_type = "list"
        else:
            chunk_type = "text"

        chunks.append({
            "text": text,
            "title": current_title,
            "token_count": token_count,
            "type": chunk_type
        })
        buffer.clear()
        buffer_tokens = 0

    for line in lines:
        line = line.rstrip()

        # Phát hiện mở/đóng code block → không cắt ngang
        if line.startswith("```"):
            in_code_block = not in_code_block

        # Heading → luôn flush chunk cũ và bắt đầu chunk mới
        if re.match(r'^#{1,4}\s', line):
            flush_buffer()
            heading_level = len(line) - len(line.lstrip('#'))
            current_title = line.lstrip("# ").strip()
            if not current_title:
                current_title = f"Heading cấp {heading_level}"

        # Gom dòng vào buffer
        buffer.append(line)
        buffer_tokens += len(encoding.encode(line + "\n"))

        # Nếu buffer quá dài và không phải đang trong code block → cắt luôn
        if buffer_tokens > 512 and not in_code_block:
            flush_buffer()

    # Äá»«ng quĂªn chunk cuá»‘i cĂ¹ng
    flush_buffer()
    return chunks

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
) -> None:
    """
    Thêm hoặc cập nhật một file markdown vào vector store
    - Xóa hết chunk cũ của file đó trước
    - Chunk thông minh
    - Add tá»«ng batch nhá» Ä‘á»ƒ trĂ¡nh treo khi file siĂªu to
    """
    coll = get_collection()
    clean_name = (source_name or Path(filename).name).strip()
    if not clean_name:
        clean_name = Path(filename).name or "document.md"

    # Xóa toàn bộ chunk cũ của file này (nếu có)
    coll.delete(where={"source": clean_name})
    # Xử lý chunk b3
    chunks = smart_chunk(file_content, filename)
    if not chunks:
        print(f"No chunks generated from {filename}")
        return
    """"""
    docs = [c["text"] for c in chunks]
    metadatas = [{
        "source": clean_name, #Tên file gốc → biết chunk này đến từ file nào, dùng để filter khi user nhắc tới file cụ thể (forced_file mode).
        "title": c["title"], #Tên heading của chunk → dùng để hiển thị, phân loại, biết chunk này thuộc phần nào trong file.
        "title_clean": re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', c["title"].lower())).strip(),
        "chunk_type": c["type"],
        "token_count": c["token_count"],
        "created_at": datetime.now().isoformat(),
        "version": version
    } for c in chunks]

    # Tạo ID duy nhất cho từng chunk:
    id_prefix = _build_chunk_id_prefix(clean_name)
    ids = [f"{id_prefix}__{i:05d}" for i in range(len(chunks))]

    # Add từng batch 50 chunk để không bị lag khi file 10k+ dòng
    batch_size = 50
    for i in range(0, len(docs), batch_size):
        coll.add(
            documents=docs[i:i+batch_size],
            metadatas=metadatas[i:i+batch_size],
            ids=ids[i:i+batch_size]
        )

    print(f"Added {len(chunks)} chunks from {clean_name} (version {version})")
    _rebuild_bm25()          # cập nhật BM25
    inject_bot_rule()        # đảm bảo rule vẫn sống


# b5. INJECT BOT RULE dá»±a vĂ o file bot-rule.md Ä‘á»ƒ Äáº£m báº£o khi LLM láº¥y context, rule luĂ´n Ä‘Æ°á»£c Æ°u tiĂªn 
def inject_bot_rule(force_full: bool = False):
    """
    Chèn/cập nhật nội quy bot vào Chroma
    - force_full=True → dùng bản dài (dùng khi context còn rộng)
    - Mặc định dùng bản ngắn để tiết kiệm token
    """
    try:
        coll = get_collection()
    except Exception as exc:
        print(f"Bo qua inject_bot_rule vi vector store chua san sang: {exc}")
        return

    rule_text = get_bot_rule_text() if force_full else BOT_RULE_SHORT
    coll.upsert(
        ids=[BOT_RULE_ID],
        documents=[rule_text],
        metadatas=[{
            "source": "BOT_RULE",
            "title": "Ná»™i quy & giá»ng Ä‘iá»‡u bot",
            "priority": 999999,
            "is_rule": True,
            "created_at": datetime.now().isoformat()
        }]
    )

# 6. HYBRID SEARCH dùng để truy vấn tài liệu với hybrid search (vector + BM25) và ép bot-rule lên đầu.
@lru_cache(maxsize=500)
def _cached_embedding(query: str):
    """Cache embedding cá»§a query â†’ vector search nhanh hÆ¡n ráº¥t nhiá»u"""
    return get_embedding_function()([query])[0]
# b4 Truy vấn tài liệu với hybrid search (vector + BM25) và ép bot-rule lên đầu.
def query_documents(
    query: str,
    user_id: str = "default",
    n_results: int = 8,
    alpha: float = 0.75  # 0.0 = chá»‰ BM25, 1.0 = chá»‰ vector. 0.75 thÆ°á»ng ngon nháº¥t
) -> Tuple[List[str], List[dict], Dict]:
    """
    Hybrid search + ép bot-rule lên đầu + lưu session
    Tráº£ vá»:
        docs, metas, extra_info (session, stats, sources)
    """
    start = time.time()
    STATS["total_queries"] += 1

    coll = get_collection()
    _rebuild_bm25()  # đảm bảo BM25 mới nhất

   # vector search đầu tiên để lấy candidates
    vec = coll.query(
        query_texts=[query],
        n_results=n_results + 15,   # lấy dư để hybrid tốt hơn
        include=["documents", "metadatas", "distances"]
    )

    v_ids = vec["ids"][0]
    v_distances = vec["distances"][0]   # cosine distance: 0 = giống, 2 = khác

    # Chuyển distance → similarity (0-1)
    cosine_sim = [1.0 - d for d in v_distances]
    if max(cosine_sim) > min(cosine_sim):
        norm_cosine = [(x - min(cosine_sim)) / (max(cosine_sim) - min(cosine_sim) + 1e-8) for x in cosine_sim]
    else:
        norm_cosine = [1.0] * len(cosine_sim)

    #BM25 scores cho tất cả document trong collection
    bm25_raw = _bm25.get_scores(query.lower().split()) if _bm25 else []
    id_to_bm25 = {doc_id: bm25_raw[i] for i, doc_id in enumerate(_all_ids)}
    max_bm25 = max(id_to_bm25.values(), default=1)
    norm_bm25 = {k: v / max_bm25 if max_bm25 > 0 else 0 for k, v in id_to_bm25.items()}

    # hybrid_scores dùng để kết hợp 2 điểm số
    hybrid_scores: Dict[str, float] = {}
    for i, doc_id in enumerate(v_ids):
        c_score = norm_cosine[i]
        b_score = norm_bm25.get(doc_id, 0)
        hybrid_scores[doc_id] = alpha * c_score + (1 - alpha) * b_score

    # Lấy top candidates
    top_ids = [x[0] for x in sorted(hybrid_scores.items(), key=lambda x: x[1], reverse=True)[:n_results + 5]]

    # Lấy nội dung thật
    results = coll.get(ids=top_ids, include=["documents", "metadatas"])
    docs = results["documents"]
    metas = results["metadatas"]

    # cho bot rule luôn đứng đầu
    rule_doc = None
    rule_meta = None
    normal_docs = []
    normal_metas = []

    for d, m in zip(docs, metas):
        if m.get("source") == "BOT_RULE" or BOT_RULE_ID in str(m.get("id", "")):
            rule_doc = d
            rule_meta = m
        else:
            normal_docs.append(d)
            normal_metas.append(m)

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
        "retrieved_ids": top_ids[:n_results]
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
    global _bm25, _last_count
    _bm25 = None
    _last_count = -1
    SESSION_MEMORY.clear()
    STATS["popular_files"].clear()
    STATS["total_queries"] = 0
    print("Da reset toan bo vector store!")
    inject_bot_rule()          # rule vẫn sống sau reset
# 8. Láº¤Y THá»NG KĂ
def get_stats():
    """Lấy thống kê để hiển thị dashboard"""
    uptime = time.time() - STATS["start_time"]
    return {
        **STATS,
        "uptime_hours": round(uptime / 3600, 2),
        "qps": round(STATS["total_queries"] / max(uptime, 1), 2)
    }

# KHá»I Táº O AN TOĂ€N KHI CẦN
def initialize_vectorstore():
    coll = get_collection()
    # Äáº£m báº£o load bot rule
    inject_bot_rule()
    print("Bot-rule da duoc inject - luon dung top 1")
    if coll.count() > 0:
        _rebuild_bm25()
        print(f"Warm-up BM25 thanh cong voi {coll.count()} chunks")
    else:
        print("Vector store hien dang trong - cho add tai lieu dau tien")
    print("="*70)
    print("VECTOR STORE v2.0 DA KHOI DONG HOAN TOAN")
    print("- Hybrid search da chuan hoa - Bot-rule bat tu - Session memory - Logging")
    print("- Toc do ~1.0-1.8s/query - RAM nhe - Enterprise ready")
    print("="*70)
