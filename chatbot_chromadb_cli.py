# chatbot_chromadb_cli.py
# Chatbot CLI tìm kiếm dữ liệu Sổ tay sinh viên ICTU bằng ChromaDB

from pathlib import Path

try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:
    raise SystemExit(
        "Thiếu thư viện. Cài bằng lệnh:\n"
        "pip install chromadb sentence-transformers"
    )


# =========================
# CẤU HÌNH
# =========================
CHROMA_DIR = Path("data/chroma_db")
COLLECTION_NAME = "ictu_student_handbook"
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

TOP_K = 5


def load_collection():
    embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=MODEL_NAME
    )

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    collection = client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_func
    )

    return collection


def search(collection, question: str):
    results = collection.query(
        query_texts=[question],
        n_results=TOP_K,
        include=["documents", "metadatas", "distances"]
    )

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    distances = results["distances"][0]

    return list(zip(docs, metas, distances))


def main():
    print("Đang tải ChromaDB...")
    collection = load_collection()

    print("Chatbot ICTU đã sẵn sàng.")
    print("Gõ câu hỏi hoặc nhập 'exit' để thoát.\n")

    while True:
        question = input("Bạn hỏi: ").strip()

        if question.lower() in ["exit", "quit", "q"]:
            break

        if not question:
            continue

        results = search(collection, question)

        print("\nKết quả liên quan nhất:\n")

        for i, (doc, meta, distance) in enumerate(results, 1):
            print(f"[{i}] {meta.get('title', '')}")
            print(f"Nguồn: {meta.get('source', '')}")
            print(f"Distance: {distance:.4f}")
            print(doc[:1500])
            print("-" * 80)

        print()


if __name__ == "__main__":
    main()
