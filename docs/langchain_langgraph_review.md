# Review va chuan hoa kien truc LangChain + LangGraph

## Muc tieu

Tai lieu nay tong hop 2 viec:

- review kien truc hien tai cua du an theo goc nhin MVC, RAG, LangChain, LangGraph
- ghi lai cac buoc refactor da thuc hien de dua code ve huong de mo rong va de bao tri hon

## Danh gia tong quan hien tai

### MVC

Nhung diem dang dung:

- `controllers/` da giu vai tro nhan request va dieu huong web/api.
- `views/` da tach rieng HTML/template va payload builder.
- `models/` co DTO cho request/response va cac object RAG.
- phan nghiep vu chinh da duoc dat trong `services/`.

Nhung diem chua sach:

- `services/chat_service.py` van vua chua graph node, vua orchestration, vua save history. Day la dau hieu application service va workflow node dang bi tron.
- `controllers/web_controller.py` van goi truc tiep `get_collection().delete(...)`, nghia la controller dang cham vao data access thay vi di qua service.
- `services/document_service.py` dang dong ca application flow, file system handling, vector indexing va admin payload.

Ket luan:

- Du an dang o muc "MVC thuc dung", chua phai MVC sach va chat.
- Can tiep tuc tach `chat graph`, `document ingestion`, `vector store gateway` thanh cac module nho hon.

### RAG

Nhung diem dang dung:

- da co ingestion cho seed corpus va upload corpus trong `services/document_service.py`
- da co preprocessing/chunking/embedding/index trong `services/vector_store_service.py`
- da co vector store, lexical fallback, web knowledge cache va web search
- da co retrieval planning, routing, prompt building va generation
- da co luu metadata `tool_name`, `source`, `level`, `word_count` de quan sat retrieval tot hon

Nhung diem chua toi uu:

- nhieu retrieval strategy truoc day bi don vao `services/rag_service.py`, kho test va kho mo rong.
- pipeline ingestion chua tach thanh cac stage rieng ten ro rang nhu `loader -> splitter -> embedder -> indexer`.
- contract metadata giua lexical retrieval, vector retrieval va web retrieval truoc day chua dong nhat.

Ket luan:

- Du an da co du thanh phan cot loi cua RAG.
- Sau refactor moi, retrieval dang tien gan hon den cau truc RAG chuan va dong nhat metadata tot hon.

### LangChain

Nhung diem dang dung sau refactor:

- prompt routing va prompt planning da dung `ChatPromptTemplate`
- parser da dung `JsonOutputParser` va `StrOutputParser`
- retrieval da duoc dua ve `BaseRetriever` qua `services/langchain_retrievers.py`
- model invocation da duoc dua ve `BaseChatModel` qua `FallbackChatModel` trong `services/langchain_service.py`

Nhung diem con no:

- `services/llm_service.py` van la backend adapter tu viet, chua tach rieng thanh `infrastructure/llm`.
- chua dung cac integration package chuyen biet cho provider, vi hien tai uu tien tai su dung co che fallback Groq/Ollama san co.
- ingestion pipeline chua dung `Runnable` chain, moi uu tien retrieval + prompting + model invocation.

Ket luan:

- Du an hien tai da co "LangChain core standard" cho prompt, parser, retriever, chat model.
- Day chua phai full LangChain ecosystem, nhung da dung huong de tiep tuc nang cap.

### LangGraph

Nhung diem dang dung:

- `services/graph_service.py` da dung `StateGraph`
- state duoc typed bang `ChatGraphState`
- graph flow ro: `normalize -> persist_user -> guardrails -> route/retrieve -> generate -> finalize`
- co sequential fallback khi moi truong khong co `langgraph`

Nhung diem con no:

- node function van nam trong `services/chat_service.py`, chua tach thanh `graph/nodes.py`
- graph builder va nghiep vu chat van con gan nhau
- chua co reducer/state helper rieng cho memory, audit, tool traces

Ket luan:

- Du an da dung LangGraph that su, khong phai chi dat ten "graph".
- Tuy nhien van nen tach nodes va state management ro hon o pha tiep theo.

## Cac refactor da thuc hien

### 1. Chuan hoa prompt va model invocation theo LangChain

Da cap nhat `services/langchain_service.py`:

- bo sung `FallbackChatModel(BaseChatModel)` de boc `generate_content_with_fallback`
- chain hien tai chay theo huong `ChatPromptTemplate -> BaseChatModel -> OutputParser`
- giu lai thong tin `used_model` trong `response_metadata`

Y nghia:

- prompt layer khong con phai tu tay convert payload roi goi adapter mot cach rong rai
- de nang cap them structured output, tool calling, retry policy hoac tracing sau nay

### 2. Chuan hoa retriever theo LangChain

Da them `services/langchain_retrievers.py`:

- `CorpusLexicalRetriever`
- `VectorStoreRetriever`
- `WebKnowledgeRetriever`
- `WebSearchRetriever`

Y nghia:

- `rag_service` khong con phai tu tao retrieval object theo tung nhanh logic
- metadata tu local/web/vector retrieval da dong nhat hon
- de thay retriever hoac test retriever doc lap hon

### 3. Chuyen router/planner sang prompt chain co parser ro rang

Da cap nhat `services/rag_service.py`:

- router tool dung `ChatPromptTemplate` + JSON parser flow
- retrieval planner dung `ChatPromptTemplate` + JSON parser flow
- context builder co helper chung de quy ve `RAGResult`

Y nghia:

- giam logic parse prompt/response thu cong
- de kiem soat schema dau ra va test planner/router ro hon

### 4. Chuan hoa ingestion bo sung seed corpus + upload corpus

Da cap nhat `services/document_service.py`:

- re-ingest khong chi nap upload ma nap ca seed corpus va upload corpus
- cache RAG corpus duoc clear sau cac thao tac ingestion/index

Y nghia:

- giam nguy co vector store mat dong bo voi file system
- dam bao flow ingestion day du hon theo chuan RAG

### 5. Chuan hoa chunk metadata

Da cap nhat `services/vector_store_service.py`:

- chunking su dung runtime config `chunk_size`, `chunk_overlap`
- metadata bo sung `level` va `word_count`

Y nghia:

- ingestion toi sat runtime config hon
- vector manager va retrieval de quan sat hon

## Nhung van de con ton tai

### Van de uu tien cao

- `services/chat_service.py` van gom qua nhieu vai tro. Nen tach thanh:
  - `services/chat_graph_nodes.py`
  - `services/chat_orchestrator.py`
  - `services/chat_result_service.py`
- `controllers/web_controller.py` can bo xoa truy cap truc tiep vao collection.
- `services/rag_service.py` van kha lon. Nen tach tiep thanh:
  - `services/rag_router.py`
  - `services/rag_flow_planner.py`
  - `services/rag_retrieval_service.py`
  - `services/rag_context_builder.py`

### Van de trung binh

- `services/llm_service.py` nen dua ve `services/llm/backends.py` va `services/llm/model_registry.py`
- document ingestion nen tach ro `loader`, `normalizer`, `splitter`, `indexer`
- web knowledge cache va web search hien con o cung tang service nghiep vu, co the tach gateway ro hon

## Cau truc de xuat cho pha tiep theo

De tranh breaking change lon, pha nay chua rename toan bo thu muc. Cau truc nen huong toi:

```text
controllers/
views/
models/
services/
  chat/
    orchestrator.py
    graph.py
    nodes.py
    state.py
  rag/
    router.py
    flow_planner.py
    retrievers.py
    retrieval_service.py
    context_builder.py
    ingestion.py
  llm/
    backends.py
    fallback_model.py
  knowledge/
    web_search_service.py
    web_knowledge_service.py
  storage/
    vector_store.py
    chat_history.py
config/
tools/
tests/
```

## Trang thai hien tai sau khi refactor

Co the xem du an hien tai la:

- MVC: tam on, nhung chua tach triet de application/service/infrastructure
- RAG: da day du cac thanh phan cot loi
- LangChain: da co prompt, parser, retriever, chat model theo `langchain-core`
- LangGraph: da co graph thuc su bang `StateGraph`

Noi ngan gon: du an da duoc dua len muc "LangChain + LangGraph dung huong va co the mo rong", nhung van con mot pha nua de dat toi muc clean architecture ro rang hon.
