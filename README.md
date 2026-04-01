# ICTU Student Assistant

Chatbot tra cuu hoc vu va van ban sinh vien duoc xay dung bang Flask, LangChain, LangGraph, FAISS va SQLite.

## Tai Lieu Do An

- Bao cao chi tiet dang duoc duy tri tai `BAO_CAO_DO_AN.md`.
- Ban Word dong bo de nop hoac chinh sua: `bao_cao_do_an_ictu_student_assistant.docx`.
- Script dong bo Markdown sang DOCX: `sync_report_docx.ps1`.

Quy uoc cap nhat tai lieu:

1. Cap nhat `README.md` khi co thay doi ve kien truc, cau truc repo, pipeline hoac cach van hanh.
2. Cap nhat `BAO_CAO_DO_AN.md` khi co thay doi lon lien quan den qua trinh thuc hien, chuc nang, ket qua hoac danh gia do an.
3. Chay `.\sync_report_docx.ps1` de tao lai file Word sau khi da cap nhat noi dung Markdown.

## Kien truc hien tai

Du an da duoc chuan hoa theo huong MVC + service layer:

- `app/routes/`: controller layer, chi nhan request/response.
- `app/models/`: persistence layer, hien tai la SQLite cho lich su chat.
- `app/services/`: business logic, gom chat orchestration, history service, RAG service, LLM client va reranker.
- `app/data/`: ingest/build/load vector store.
- `templates/`, `static/`: giao dien.

## Luong RAG

1. User gui cau hoi qua `/chat`.
2. `chat_service` lay lich su hoi thoai va goi `rag_service`.
3. `rag_service` chay LangGraph voi 4 buoc:
   - build memory
   - route cau hoi (`handbook` / `policy` / `faq`)
   - retrieve tai lieu bang LangChain retriever
   - generate cau tra loi bang Ollama
4. Ket qua duoc luu vao SQLite va tra ve frontend.

## Cac script chinh

- `clean_data_to_md.py`: wrapper chay `app.data.clean_raw`.
- `prepare_rag_md.py`: chuan hoa markdown de retriever chunk tot hon.
- `data_pipeline.py`: wrapper chay `app.data.pipeline`.

## Thu muc du lieu

- `datadoan/`: file nguon PDF/DOCX/XLS/DOC.
- `clean_md/`: markdown da lam sach sau khi convert tu file nguon.
- `rag_md/`: markdown toi uu cho RAG.
- `data/`: corpora da duoc chia theo 3 route `policy` / `handbook` / `faq`.
- `vector_db/`: FAISS stores.

## Cai dat

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Neu dung `.env`, du an se tu nap bien moi truong nho `python-dotenv`.

## Bien moi truong

Co the copy tu `.env.example`:

- `FLASK_SECRET_KEY`
- `FLASK_DEBUG`
- `FLASK_USE_RELOADER`
- `CHAT_DB_NAME`
- `RAW_DATA_DIR`
- `CLEAN_MD_DIR`
- `RAG_MD_DIR`
- `TXT_DATA_DIR`
- `VECTOR_DB_DIR`
- `OLLAMA_URL`
- `OLLAMA_MODEL`
- `EMBEDDINGS_MODEL`
- `ENABLE_NEURAL_RERANKER`
- `NEURAL_RERANKER_MODEL`

Mac dinh `ENABLE_NEURAL_RERANKER=0` de tranh loi `torch` / `DLL` tren Windows.
Neu moi truong cua ban chay on dinh voi `sentence-transformers`, co the bat lai bang `ENABLE_NEURAL_RERANKER=1`.
Mac dinh `FLASK_USE_RELOADER=0` de tranh vong lap reload tren Windows khi `watchdog` theo doi `site-packages`.

## Chuan bi du lieu

1. Chuyen file nguon thanh markdown da lam sach:

```bash
python clean_data_to_md.py
```

Neu can rebuild rieng kho `policy` tu `datadoan/`:

```bash
python clean_data_to_md.py --route policy --ocr auto
```

Script se uu tien `PyPDF2`, va tren Windows se tu fallback sang OCR built-in khi PDF gan nhu khong extract duoc text.

2. Toi uu markdown cho RAG:

```bash
python prepare_rag_md.py
```

Neu chi muon lam moi lai `policy`:

```bash
python prepare_rag_md.py --route policy
```

3. Build vector store route-based:

```bash
python data_pipeline.py build
```

Hoac rebuild toan bo corpora va vector stores:

```bash
python data_pipeline.py rebuild
```

Neu chi muon chia lai corpora va cap nhat thong ke ma chua build vector:

```bash
python data_pipeline.py prepare
python data_pipeline.py stats
```

Du an van co fallback doc `vector_db/` legacy neu ban chua build lai multi-store.

## Chay ung dung

```bash
python run.py
```

Truy cap:

- `http://127.0.0.1:5000/`
- `http://127.0.0.1:5000/chat-ui`
- `http://127.0.0.1:5000/history`

## Ghi chu

- `upload`, `vector`, `config` hien la cac trang giao dien placeholder, chua co backend day du.
- Luong chat chinh hien tai di qua `app/services/rag_service.py`.
- `app/services/reranker.py` mac dinh dung lexical fallback; neural reranker la tuy chon va co the bat bang bien moi truong.
- `clean_md/_reports/*.json` va `rag_md/_reports/*.json` se ghi lai thong ke lan rebuild gan nhat, gom ca so file OCR fallback va file legacy `.doc` / `.xls` chua duoc parse.
