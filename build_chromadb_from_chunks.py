# build_chromadb_from_chunks.py
# Mục đích:
# - Đọc file data/chunks.jsonl đã tạo từ PDF/Markdown sạch
# - Tạo ChromaDB để dùng cho chatbot/RAG
# - Thay cho FAISS, gọn hơn vì ChromaDB lưu luôn document + metadata

import json
from pathlib import Path

try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:
    raise SystemExit(
        "Thiếu thư viện ChromaDB. Cài bằng lệnh:\n"
        "pip install chromadb sentence-transformers"
    )


# =========================
# CẤU HÌNH
# =========================
CHUNK_FILE = Path("data/chunks.jsonl")
CHROMA_DIR = Path("data/chroma_db")

COLLECTION_NAME = "ictu_student_handbook"

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def load_chunks():
    if not CHUNK_FILE.exists():
        raise FileNotFoundError(
            f"Không tìm thấy {CHUNK_FILE}. "
            "Hãy chạy file rebuild_data_from_original_pdf.py trước."
        )

    chunks = []
    with CHUNK_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line))

    return chunks


def main():
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    print("Đang đọc chunks...")
    chunks = load_chunks()

    if not chunks:
        print("Không có dữ liệu chunks.")
        return

    print(f"Tổng chunks: {len(chunks)}")

    embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=MODEL_NAME
    )

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    # Xóa collection cũ để build lại sạch
    try:
        client.delete_collection(COLLECTION_NAME)
        print("Đã xóa collection cũ.")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_func,
        metadata={"description": "ICTU student handbook RAG database"}
    )

    ids = []
    documents = []
    metadatas = []

    for item in chunks:
        ids.append(str(item["id"]))
        documents.append(item["content"])
        metadatas.append({
            "title": item.get("title", ""),
            "source": item.get("source", ""),
        })

    batch_size = 200

    print("Đang thêm dữ liệu vào ChromaDB...")
    for i in range(0, len(documents), batch_size):
        collection.add(
            ids=ids[i:i + batch_size],
            documents=documents[i:i + batch_size],
            metadatas=metadatas[i:i + batch_size],
        )
        print(f"Đã thêm {min(i + batch_size, len(documents))}/{len(documents)} chunks")

    print("\nHoàn tất.")
    print(f"ChromaDB lưu tại: {CHROMA_DIR.resolve()}")
    print(f"Collection: {COLLECTION_NAME}")


if __name__ == "__main__":
    main()
