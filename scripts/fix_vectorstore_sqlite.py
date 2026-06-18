import sqlite3
import re
import os

def fix_sqlite_windows_paths():
    db_path = "vectorstore/chroma.sqlite3"
    if not os.path.exists(db_path):
        print(f"No sqlite db found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT id, schema_str FROM collections").fetchall()
    
    updated = False
    for row_id, schema_str in rows:
        if schema_str and "C:\\\\" in schema_str:
            # Replaces the whole Windows path inside the JSON with the raw model name
            new_schema = re.sub(r'C:\\\\[^"]+', 'paraphrase-multilingual-MiniLM-L12-v2', schema_str)
            conn.execute("UPDATE collections SET schema_str = ? WHERE id = ?", (new_schema, row_id))
            updated = True
            print(f"Fixed Windows path in collection {row_id}")
            
    if updated:
        conn.commit()
        print("Successfully updated vectorstore sqlite metadata.")
    else:
        print("No Windows paths found in vectorstore metadata.")

    conn.close()

if __name__ == "__main__":
    fix_sqlite_windows_paths()
