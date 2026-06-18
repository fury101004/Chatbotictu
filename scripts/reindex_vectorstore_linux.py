import os
import shutil

try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:
    print("ChromaDB not installed, skipping re-index.")
    exit(0)

def main():
    print("Re-indexing ChromaDB to fix Windows paths...")
    vectorstore_path = "vectorstore"
    backup_path = "vectorstore_backup"

    if not os.path.exists(vectorstore_path) or not os.listdir(vectorstore_path):
        print(f"No vectorstore found at {vectorstore_path}, nothing to migrate.")
        return

    # Backup old db
    shutil.copytree(vectorstore_path, backup_path)
    shutil.rmtree(vectorstore_path)
    os.makedirs(vectorstore_path, exist_ok=True)

    # Initialize clients
    old_client = chromadb.PersistentClient(path=backup_path)
    new_client = chromadb.PersistentClient(path=vectorstore_path)

    # We use a built-in embedding function just so get_collection doesn't crash 
    # trying to unpickle a Windows path one from the old sqlite metadata
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="paraphrase-multilingual-MiniLM-L12-v2"
    )

    collections = old_client.list_collections()
    if not collections:
        print("No collections found to migrate.")
        shutil.rmtree(backup_path)
        return

    for col in collections:
        col_name = col.name
        print(f"Migrating collection: {col_name}")
        old_collection = old_client.get_collection(name=col_name, embedding_function=ef)
        
        # Get all data.
        data = old_collection.get(include=["embeddings", "documents", "metadatas"], limit=100000)
        
        # Recreate collection in new DB
        # We explicitly set basic metadata to avoid copying over any bad paths
        # from old_collection.metadata if it had any.
        new_collection = new_client.create_collection(
            name=col_name,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"}
        )
        
        ids = data.get("ids", [])
        if not ids:
            print(f"Collection {col_name} is empty.")
            continue
            
        print(f"Found {len(ids)} items in {col_name}")
        
        batch_size = 500
        for i in range(0, len(ids), batch_size):
            new_collection.add(
                ids=ids[i:i+batch_size],
                embeddings=data["embeddings"][i:i+batch_size] if data.get("embeddings") else None,
                documents=data["documents"][i:i+batch_size] if data.get("documents") else None,
                metadatas=data["metadatas"][i:i+batch_size] if data.get("metadatas") else None
            )
            print(f"Added {min(i+batch_size, len(ids))}/{len(ids)} to {col_name}")

    print("Re-indexing complete. Removing backup...")
    shutil.rmtree(backup_path)

if __name__ == "__main__":
    main()
