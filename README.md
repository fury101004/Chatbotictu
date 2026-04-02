# ICTU Student Assistant

Chatbot tra cuu hoc vu va van ban sinh vien duoc xay dung bang FastAPI, LangChain, LangGraph, FAISS va SQLite.

## Tai Lieu Do An

- Bao cao chi tiet dang duoc duy tri tai `BAO_CAO_DO_AN.md`.
- Ban Word dong bo de nop hoac chinh sua: `bao_cao_do_an_ictu_student_assistant.docx`.
- Script dong bo Markdown sang DOCX: `sync_report_docx.ps1`.

Quy uoc cap nhat tai lieu:

1. Cap nhat `README.md` khi co thay doi ve kien truc, cau truc repo, pipeline hoac cach van hanh.
2. Cap nhat `BAO_CAO_DO_AN.md` khi co thay doi lon lien quan den qua trinh thuc hien, chuc nang, ket qua hoac danh gia do an.
3. Chay `.\sync_report_docx.ps1` de tao lai file Word sau khi da cap nhat noi dung Markdown.

## Kien truc hien tai

Du an duoc to chuc lai theo huong FastAPI + service layer:

- `main.py`: entrypoint chinh, tao ung dung FastAPI, mount static va dang ky routers.
- `app/core/`: cau hinh trung tam va bien moi truong.
- `app/api/`: API routes cho chat, history, knowledge base.
- `app/web/`: page routes, context cho template va rendering giao dien.
- `app/models/`: persistence layer, hien tai la SQLite cho lich su chat.
- `app/services/`: business logic, gom chat orchestration, history service, RAG service, knowledge upload, LLM client va reranker.
- `app/prompts/`: thu vien prompt cho route va answer generation, de toi uu chatbot ma khong can sua logic retrieve.
- `app/data/`: ingest/build/load vector store.
- `templates/`, `static/`: giao dien Jinja2 + assets frontend.

## Luong RAG

1. User gui cau hoi qua `/api/chat`.
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
- `python -m app.data.pipeline`: build/rebuild vector store va corpora.

## Thu muc du lieu

- `datadoan/`: file nguon PDF/DOCX/Markdown/XLS/DOC.
- `clean_md/`: markdown da lam sach sau khi convert tu file nguon.
- `rag_md/`: markdown toi uu cho RAG.
- `data/`: corpora da duoc chia theo 3 route `policy` / `handbook` / `faq`.
- `vector_db/`: FAISS stores.

## Cai dat

```bash
python -m venv .venv
venv\Scripts\Activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Neu muon bat them xuat PDF cho lich su chat:

```bash
pip install -r requirements-optional.txt
```

Neu dung `.env`, du an se tu nap bien moi truong nho `python-dotenv`.

## Bien moi truong

Co the copy tu `.env.example`:

- `SECRET_KEY`
- `APP_ENV`
- `APP_DEBUG`
- `SERVER_HOST`
- `SERVER_PORT`
- `UVICORN_RELOAD`
- `SESSION_HTTPS_ONLY`
- `SESSION_SAME_SITE`
- `CHAT_DB_NAME`
- `RAW_DATA_DIR`
- `CLEAN_MD_DIR`
- `RAG_MD_DIR`
- `TXT_DATA_DIR`
- `VECTOR_DB_DIR`
- `UPLOADS_DIR_NAME`
- `MAX_UPLOAD_SIZE_MB`
- `LLM_PROVIDER`
- `OLLAMA_URL`
- `OLLAMA_MODEL`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `EMBEDDINGS_MODEL`
- `ENABLE_NEURAL_RERANKER`
- `NEURAL_RERANKER_MODEL`

App doc truc tiep `SECRET_KEY`, `APP_ENV`, `APP_DEBUG`, `UVICORN_RELOAD`.
Neu dat `APP_ENV=production`, app se fail fast neu `SECRET_KEY` van de trong hoac dang dung gia tri mac dinh khong an toan.

`LLM_PROVIDER` ho tro `ollama`, `gemini` va `auto`.
Voi `auto`, app uu tien Gemini neu `GEMINI_API_KEY` da duoc cau hinh, nguoc lai se dung Ollama.
Neu muon ep dung Gemini, dat:

```bash
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-api-key-here
GEMINI_MODEL=gemini-1.5-flash
```

Mac dinh `ENABLE_NEURAL_RERANKER=0` de tranh loi `torch` / `DLL` tren Windows.
Neu moi truong cua ban chay on dinh voi `sentence-transformers`, co the bat lai bang `ENABLE_NEURAL_RERANKER=1`.
Mac dinh `UVICORN_RELOAD=0` de tranh reload ngoai y muon tren moi truong Windows.

## Chuan bi du lieu

1. Chuyen file nguon thanh markdown da lam sach:

```bash
python clean_data_to_md.py
```

Neu can rebuild rieng kho `policy` tu `datadoan/`:

```bash
python clean_data_to_md.py --route policy --ocr auto
```

Script se uu tien `PyPDF2`, va tren Windows se tu fallback sang OCR built-in khi PDF gan nhu khong extract duoc text. Nguon `.md` se duoc giu noi dung, chuan hoa whitespace va bo sung frontmatter khi can.

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
python -m app.data.pipeline build
```

Hoac rebuild toan bo corpora va vector stores:

```bash
python -m app.data.pipeline rebuild
```

Neu chi muon chia lai corpora va cap nhat thong ke ma chua build vector:

```bash
python -m app.data.pipeline prepare
python -m app.data.pipeline stats
```

Du an van co fallback doc `vector_db/` legacy neu ban chua build lai multi-store.

## Upload file tu giao dien

Trang `http://127.0.0.1:5000/upload` da co backend upload:

1. Chon route `policy` hoac `handbook`.
2. Upload file `PDF` / `DOCX` / `Markdown (.md)`.
3. App se luu file vao `RAW_DATA_DIR/_uploads/<route>/`.
4. He thong tao background knowledge job, build tren staging workspace, sau do moi publish sang du lieu live.
5. Frontend tu poll trang thai job cho den khi clean markdown, rag markdown, corpora va vector store hoan tat.

Trang `http://127.0.0.1:5000/vector` dung de theo doi trang thai route va rebuild toan bo kho du lieu khi can.

## Chay ung dung

```bash
python main.py
```

Truy cap:

- `http://127.0.0.1:5000/`
- `http://127.0.0.1:5000/chat`
- `http://127.0.0.1:5000/history`

## Ghi chu

- `upload` va `vector` da duoc noi backend de upload file va rebuild vector store ngay tren giao dien.
- Upload/rebuild khong con chay inline trong request; moi thao tac se tao knowledge job va UI se theo doi tien do qua `/api/knowledge/jobs/{job_id}`.
- Build kho tri thuc da chuyen sang mo hinh staging -> publish de tranh ghi do dang vao du lieu live khi pipeline loi.
- FAISS store, embeddings va retriever duoc cache trong process va tu invalid sau khi rebuild hoac upload thanh cong.
- `config` van la trang tham khao, cac gia tri duoc doc tu `.env` / environment variables.
- Luong chat chinh hien tai di qua `app/services/rag_service.py`.
- `app/services/reranker.py` mac dinh dung lexical fallback; neural reranker la tuy chon va co the bat bang bien moi truong.
- `clean_md/_reports/*.json` va `rag_md/_reports/*.json` se ghi lai thong ke lan rebuild gan nhat, gom ca so file OCR fallback va file legacy `.doc` / `.xls` chua duoc parse.
- Export PDF cho lich su chat la tuy chon; neu chua cai `reportlab`, app van khoi dong binh thuong va endpoint PDF se tra loi ro rang.
- Uu tien chay bang `uvicorn` thong qua `python main.py`; app khong con giu wrapper entrypoint phu nua.
