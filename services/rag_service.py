from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional
import json
import re
import unicodedata

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

from config.rag_tools import (
    DEFAULT_RAG_TOOL,
    FALLBACK_RAG_NODE,
    QA_ROOT,
    RAG_TOOL_ORDER,
    RAG_TOOL_PROFILES,
    RAG_UPLOAD_ROOT,
    get_tool_corpus_paths,
)
from models.chat import RAGResult, RetrievedChunk
from services.ictu_scope_service import ICTU_SCOPE_REPLY_VI, is_ictu_related_query
from services.langchain_service import invoke_json_prompt_chain
from services.langchain_retrievers import (
    CorpusLexicalRetriever,
    VectorStoreRetriever,
    WebKnowledgeRetriever,
    WebSearchRetriever,
)
from services.llm_service import get_model, llm_network_available
from services.vector_store_service import SESSION_MEMORY, embedding_backend_ready, get_collection, inject_bot_rule, query_documents
from services.web_knowledge_service import search_trusted_web_knowledge
from services.web_search import search_web_ictu, should_use_web_search


@dataclass(slots=True)
class CorpusDocument:
    path: Path
    source: str
    title: str
    text: str
    text_lower: str
    normalized_text: str
    normalized_title: str
    normalized_source: str
    token_set: frozenset[str]


RETRIEVAL_LOCAL_DATA = "local_data"
RETRIEVAL_WEB_SEARCH = "web_search"
RETRIEVAL_HYBRID = "hybrid"
RETRIEVAL_LOCAL_FIRST = "local_first"
RETRIEVAL_WEB_FIRST = "web_first"


@dataclass(slots=True)
class RetrievalFlowPlan:
    source: str
    priority: str
    reason: str
    confidence: float
    route: str


_RAG_ROUTER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Ban la bo dinh tuyen cho he thong RAG cua truong. "
            "Khong tra loi noi dung cau hoi. "
            "Chi tra ve JSON hop le theo format "
            '{"tool":"<tool_name>","reason":"<1 cau ngan>","confidence":0.0}.',
        ),
        (
            "human",
            "Chi duoc chon 1 trong cac tool sau:\n"
            "{tool_descriptions}\n"
            "- fallback_rag: dung khi cau hoi mo ho, khong chac chan, hoac lien quan nhieu nhom.\n\n"
            "Cau hoi nguoi dung:\n"
            "{message}",
        ),
    ]
)

_RETRIEVAL_FLOW_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Ban la bo lap ke hoach truy xuat truoc khi chatbot tra loi. "
            "Khong tra loi cau hoi cua nguoi dung. "
            "Chi tra ve JSON hop le voi cac truong source, priority, reason, confidence.",
        ),
        (
            "human",
            "Nhom tri thuc RAG da duoc router goi y:\n"
            "{current_tool}\n\n"
            "Mo ta cac nhom tri thuc:\n"
            "{tool_descriptions}\n\n"
            "Nguon co the chon:\n"
            "- local_data: dung corpus noi bo da nap, gom so tay sinh vien, quy dinh, FAQ, tai lieu upload va vector store.\n"
            "- web_search: dung tim kiem web uu tien domain chinh thuc ICTU cho thong tin moi, thong bao, lich, tin tuc, tuyen sinh, deadline, so lieu/co cau co the thay doi.\n"
            "- hybrid: lay local_data lam nen va bo sung web_search, hoac web_search truoc roi doi chieu local_data.\n\n"
            "Quy tac quyet dinh:\n"
            "- Chon local_data/local_first khi cau hoi hoi ve noi dung on dinh trong tai lieu da nap: so tay sinh vien, quy che, quy dinh, dieu kien, dinh nghia, quy trinh, cau hoi Q&A co san.\n"
            "- Chon web_search/web_first khi cau hoi co dau hieu thoi gian thuc hoac can cap nhat: hom nay, moi nhat, gan day, nam nay, thong bao moi, lich, deadline, tuyen sinh hien tai, chi tieu, hoc phi moi, tin tuc.\n"
            "- Chon hybrid khi cau hoi can ca quy dinh nen trong tai lieu noi bo va tinh trang/thong bao moi tren website.\n"
            "- Neu khong chac chan, uu tien local_data/local_first, tru khi cau hoi ro rang can thong tin moi.\n\n"
            "JSON bat buoc:\n"
            "{\n"
            '  "source": "local_data | web_search | hybrid",\n'
            '  "priority": "local_first | web_first",\n'
            '  "reason": "mot cau ngan noi ly do",\n'
            '  "confidence": 0.0\n'
            "}\n\n"
            "Cau hoi nguoi dung:\n"
            "{message}",
        ),
    ]
)



def _normalize_for_match(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    stripped = stripped.replace("đ", "d").replace("&", " va ")
    return re.sub(r"\s+", " ", stripped).strip()


def _tokenize(text: str) -> list[str]:
    normalized = _normalize_for_match(text)
    return [token for token in re.findall(r"[a-z0-9]+", normalized) if len(token) > 1]


@lru_cache(maxsize=32)
def _load_tool_corpus(tool_name: str) -> tuple[CorpusDocument, ...]:
    corpus_paths = get_tool_corpus_paths(tool_name)
    documents: list[CorpusDocument] = []
    seen_paths: set[Path] = set()

    for raw_path in corpus_paths:
        path = Path(raw_path)
        if not path.exists():
            continue

        if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt"}:
            file_paths = [path]
        elif path == QA_ROOT:
            file_paths = sorted(candidate for candidate in path.glob("*.md") if candidate.is_file())
        else:
            file_paths = sorted(
                candidate
                for candidate in path.rglob("*")
                if candidate.is_file() and candidate.suffix.lower() in {".md", ".markdown", ".txt"}
            )

        for file_path in file_paths:
            if file_path in seen_paths:
                continue
            seen_paths.add(file_path)

            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            source = _relative_source(file_path)
            title = _extract_title(text, file_path)
            text_lower = text.casefold()
            normalized_text = _normalize_for_match(text)
            normalized_title = _normalize_for_match(title)
            normalized_source = _normalize_for_match(source)
            token_set = frozenset(_tokenize(f"{title}\n{source}\n{text}"))
            documents.append(
                CorpusDocument(
                    path=file_path,
                    source=source,
                    title=title,
                    text=text,
                    text_lower=text_lower,
                    normalized_text=normalized_text,
                    normalized_title=normalized_title,
                    normalized_source=normalized_source,
                    token_set=token_set,
                )
            )

    return tuple(documents)


@lru_cache(maxsize=1)
def _load_all_tool_documents() -> tuple[CorpusDocument, ...]:
    documents: list[CorpusDocument] = []
    seen_sources: set[str] = set()
    for tool_name in RAG_TOOL_ORDER:
        for doc in _load_tool_corpus(tool_name):
            if doc.source in seen_sources:
                continue
            seen_sources.add(doc.source)
            documents.append(doc)
    return tuple(documents)



def _relative_source(path: Path) -> str:
    try:
        return path.relative_to(QA_ROOT).as_posix()
    except ValueError:
        try:
            return f"uploads/{path.relative_to(RAG_UPLOAD_ROOT).as_posix()}"
        except ValueError:
            return path.name


def clear_rag_corpus_cache(tool_name: Optional[str] = None) -> None:
    _load_all_tool_documents.cache_clear()
    if not hasattr(_load_tool_corpus, "cache_clear"):
        return
    _load_tool_corpus.cache_clear()



def _extract_title(text: str, file_path: Path) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
        if stripped.lower().startswith("title:"):
            return stripped.split(":", 1)[1].strip().strip('"')
    return file_path.stem



def _candidate_phrases(message: str) -> list[str]:
    normalized = _normalize_for_match(message)
    phrases: list[str] = []
    if normalized:
        phrases.append(normalized)

    tokens = _tokenize(normalized)
    if len(tokens) >= 2:
        phrases.extend(" ".join(tokens[i : i + 2]) for i in range(len(tokens) - 1))
    if len(tokens) >= 3:
        phrases.extend(" ".join(tokens[i : i + 3]) for i in range(len(tokens) - 2))
    return phrases[:8]



def _score_document(doc: CorpusDocument, query_tokens: list[str], query_phrases: list[str]) -> int:
    if not query_tokens:
        return 0

    unique_tokens = set(query_tokens)
    token_overlap = sum(1 for token in unique_tokens if token in doc.token_set)
    source_overlap = sum(1 for token in unique_tokens if token in doc.normalized_source)
    title_overlap = sum(1 for token in unique_tokens if token in doc.normalized_title)
    phrase_hits = sum(1 for phrase in query_phrases if len(phrase) >= 6 and phrase in doc.normalized_text)
    has_qa_marker = (
        "**q:**" in doc.text_lower
        or "**question:**" in doc.text_lower
        or bool(re.search(r"^#{1,6}\s+q\d+\.?\s+", doc.text_lower, flags=re.MULTILINE))
    )
    qa_bonus = 10 if has_qa_marker and token_overlap >= 2 else 0
    questions_file_bonus = 12 if doc.path.name.casefold().endswith(".questions.md") and token_overlap >= 2 else 0
    upload_bonus = 8 if doc.source.startswith("uploads/") and token_overlap >= 2 else 0
    year_bonus = 4 if any(year in doc.normalized_text for year in query_tokens if year.isdigit() and len(year) == 4) else 0
    bhyt_bonus = 6 if any(token in {"bhyt", "bao", "hiem", "y", "te"} for token in query_tokens) and ("bhyt" in doc.normalized_text or "bao hiem y te" in doc.normalized_text) else 0

    return (
        token_overlap * 4
        + source_overlap * 3
        + title_overlap * 2
        + phrase_hits * 5
        + qa_bonus
        + questions_file_bonus
        + upload_bonus
        + year_bonus
        + bhyt_bonus
    )



_QA_LINE_RE = re.compile(r"^\s*\*\*(?:question|q):\*\*\s*(?P<text>.+?)\s*$", flags=re.IGNORECASE)
_QA_HEADING_RE = re.compile(r"^\s*#{1,6}\s+(?:q\d+\.?\s*)?(?P<text>.+\?)\s*$", flags=re.IGNORECASE)
_QUESTION_SECTION_RE = re.compile(r"^\s*#{1,6}\s+(?:question\s+\d+|q\d+\.?)\b", flags=re.IGNORECASE)


def _extract_question_text(line: str) -> Optional[str]:
    marker_match = _QA_LINE_RE.match(line)
    if marker_match:
        return marker_match.group("text").strip()

    heading_match = _QA_HEADING_RE.match(line)
    if heading_match:
        return heading_match.group("text").strip()

    return None


def _score_qa_question(question: str, message: str, query_tokens: list[str]) -> int:
    query_set = set(query_tokens)
    if not query_set:
        return 0

    question_set = set(_tokenize(question))
    if not question_set:
        return 0

    overlap = len(query_set & question_set)
    if overlap == 0:
        return 0

    query_norm = _normalize_for_match(message)
    question_norm = _normalize_for_match(question)
    query_coverage = overlap / max(len(query_set), 1)
    question_coverage = overlap / max(len(question_set), 1)
    score = overlap * 10 + int((query_coverage + question_coverage) * 30)

    if query_norm and (query_norm in question_norm or question_norm in query_norm):
        score += 200

    return score


def _extract_best_qa_snippet(doc: CorpusDocument, message: str, query_tokens: list[str], max_chars: int) -> Optional[str]:
    lines = [line.rstrip() for line in doc.text.splitlines()]
    if not lines:
        return None

    best: Optional[tuple[int, int]] = None
    for index, line in enumerate(lines):
        question = _extract_question_text(line)
        if not question:
            continue

        score = _score_qa_question(question, message, query_tokens)
        if best is None or score > best[0]:
            best = (score, index)

    if best is None:
        return None

    query_token_count = len(set(query_tokens))
    minimum_score = max(25, min(70, query_token_count * 5))
    score, start = best
    if score < minimum_score:
        return None

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if _extract_question_text(lines[index]) or _QUESTION_SECTION_RE.match(lines[index]):
            end = index
            break

    block_lines = [line for line in lines[start:end] if line.strip()]
    snippet = "\n".join(block_lines).strip()
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars].rstrip()
    return snippet or None


def _extract_relevant_snippet(doc: CorpusDocument, message: str, query_tokens: list[str], max_chars: int = 2200) -> str:
    qa_snippet = _extract_best_qa_snippet(doc, message, query_tokens, max_chars)
    if qa_snippet:
        return qa_snippet

    lines = [line.strip() for line in doc.text.splitlines() if line.strip()]
    if not lines:
        return doc.text[:max_chars]

    matched_lines = [line for line in lines if any(token in _normalize_for_match(line) for token in query_tokens)]
    selected_lines = matched_lines[:10] if matched_lines else lines[:12]

    snippet = "\n".join(selected_lines).strip()
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars].rstrip()
    return snippet


def _documents_to_chunks(documents: list[Document]) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            document=document.page_content,
            metadata=dict(document.metadata or {}),
        )
        for document in documents
    ]


def _build_result_from_documents(
    *,
    documents: list[Document],
    tool_name: Optional[str],
    route_name: str,
    mode: str,
    target_file: Optional[str] = None,
    context_max_chunks: Optional[int] = None,
) -> RAGResult:
    chunks = _documents_to_chunks(documents)
    limited_chunks = chunks[:context_max_chunks] if context_max_chunks is not None else chunks

    context_parts: list[str] = []
    sources: list[str] = []

    for chunk in limited_chunks:
        metadata = chunk.metadata
        source = str(metadata.get("source", "") or "")
        title = str(metadata.get("title", "") or "").strip()
        context_entry = str(metadata.get("context_entry", "") or "").strip()

        if source and source != "BOT_RULE":
            extra_sources = metadata.get("sources")
            if isinstance(extra_sources, list):
                sources.extend(str(item) for item in extra_sources if item)
            else:
                sources.append(source)

        if context_entry:
            context_parts.append(context_entry)
            continue

        text = chunk.document.strip().replace("\n", " ")[:2000]
        if title and title != "Khong co tieu de":
            context_parts.append(f"[{title}]\n{text}")
        else:
            context_parts.append(text)

    context_text = "\n\n".join(context_parts) if context_parts else "Thong tin dang duoc cap nhat."
    chunks_used = len(limited_chunks)

    return RAGResult(
        context_text=context_text,
        chunks=chunks,
        target_file=target_file,
        mode=mode,
        sources=list(dict.fromkeys(source for source in sources if source)),
        chunks_used=chunks_used,
        rag_tool=tool_name,
        rag_route=route_name,
    )


def _build_result_from_matches(
    *,
    message: str,
    matches: list[tuple[int, CorpusDocument]],
    tool_name: str,
    route_name: str,
    mode: str,
) -> RAGResult:
    query_tokens = _tokenize(message)
    context_parts: list[str] = []
    sources: list[str] = []
    chunks: list[RetrievedChunk] = []

    for score, doc in matches:
        snippet = _extract_relevant_snippet(doc, message, query_tokens)
        context_parts.append(f"[{doc.title} | source: {doc.source} | score: {score}]\n{snippet}")
        sources.append(doc.source)
        chunks.append(
            RetrievedChunk(
                document=snippet,
                metadata={
                    "source": doc.source,
                    "title": doc.title,
                    "score": score,
                    "tool_name": tool_name,
                    "path": str(doc.path),
                },
            )
        )

    context_text = "\n\n".join(context_parts) if context_parts else "Thong tin dang duoc cap nhat."
    return RAGResult(
        context_text=context_text,
        chunks=chunks,
        target_file=None,
        mode=mode,
        sources=list(dict.fromkeys(sources)),
        chunks_used=len(chunks),
        rag_tool=tool_name,
        rag_route=route_name,
    )



def _build_web_search_result(message: str, route_name: str, tool_name: Optional[str]) -> Optional[RAGResult]:
    documents = WebSearchRetriever(
        search_fn=search_web_ictu,
        tool_name=tool_name or FALLBACK_RAG_NODE,
    ).invoke(message)
    if not documents:
        return None

    return _build_result_from_documents(
        documents=documents,
        tool_name=tool_name,
        route_name=route_name,
        mode="web_search",
    )


def _merge_web_search_result(local_result: RAGResult, web_result: Optional[RAGResult], *, web_first: bool = True) -> RAGResult:
    if web_result is None or not web_result.chunks:
        return local_result

    local_text = local_result.context_text.strip()
    missing_local_context = local_text in {"Thong tin dang duoc cap nhat.", ""}
    if missing_local_context:
        context_text = web_result.context_text
    elif web_first:
        context_text = f"{web_result.context_text}\n\n{local_result.context_text}"
    else:
        context_text = f"{local_result.context_text}\n\n{web_result.context_text}"

    chunks = [*web_result.chunks, *local_result.chunks] if web_first else [*local_result.chunks, *web_result.chunks]
    sources = [*web_result.sources, *local_result.sources] if web_first else [*local_result.sources, *web_result.sources]

    return RAGResult(
        context_text=context_text,
        chunks=chunks,
        target_file=local_result.target_file,
        mode=f"{local_result.mode}+web_search",
        sources=list(dict.fromkeys(sources)),
        chunks_used=local_result.chunks_used + web_result.chunks_used,
        rag_tool=local_result.rag_tool,
        rag_route=local_result.rag_route,
    )



def _build_web_knowledge_result(message: str, route_name: str, tool_name: Optional[str]) -> Optional[RAGResult]:
    documents = WebKnowledgeRetriever(
        search_fn=search_trusted_web_knowledge,
        tool_name=tool_name or FALLBACK_RAG_NODE,
    ).invoke(message)
    if not documents:
        return None

    return _build_result_from_documents(
        documents=documents,
        tool_name=tool_name,
        route_name=route_name,
        mode="web_knowledge_base",
    )



def _search_documents(documents: tuple[CorpusDocument, ...], message: str, limit: int = 4) -> list[tuple[int, CorpusDocument]]:
    query_tokens = _tokenize(message)
    query_phrases = _candidate_phrases(message)

    scored = [
        (score, doc)
        for doc in documents
        if (score := _score_document(doc, query_tokens, query_phrases)) > 0
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        return []

    top_score = scored[0][0]
    threshold = max(8, top_score - 12, int(top_score * 0.6))
    filtered = [item for item in scored if item[0] >= threshold]
    return filtered[:limit]



def _route_rag_tool_by_keyword(message: str) -> tuple[str, str]:
    message_lower = _normalize_for_match(message)
    scores: dict[str, int] = {}

    for tool_name, profile in RAG_TOOL_PROFILES.items():
        keywords = [_normalize_for_match(keyword) for keyword in profile.get("route_keywords", [])]
        score = sum(2 for keyword in keywords if keyword in message_lower)
        if tool_name == "student_faq_rag" and any(
            cue in message_lower for cue in ["khi nao", "bao gio", "o dau", "lam sao", "ntn"]
        ):
            score += 2
        if tool_name == "school_policy_rag" and any(
            cue in message_lower for cue in ["bao hiem y te", "bhyt", "chinh sach", "lan 1", "lan 2", "lan 3"]
        ):
            score += 4
        scores[tool_name] = score

    best_tool = max(scores, key=scores.get)
    best_score = scores[best_tool]

    if best_score <= 0:
        return FALLBACK_RAG_NODE, "router_fallback"

    return best_tool, f"router_keyword_score:{best_score}"


def _keyword_route_score(route_name: str) -> int:
    match = re.search(r"router_keyword_score:(\d+)", route_name)
    if not match:
        return 0
    return int(match.group(1))


def _extract_router_json(raw_text: str) -> Optional[dict]:
    if not raw_text:
        return None

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


@lru_cache(maxsize=1)
def _llm_router_network_available() -> bool:
    return llm_network_available()


def _route_rag_tool_by_llm(message: str) -> Optional[tuple[str, str]]:
    if get_model() is None or not _llm_router_network_available():
        return None

    tool_descriptions = "\n".join(
        f"- {tool_name}: {profile.get('description', profile.get('label', tool_name))}"
        for tool_name, profile in RAG_TOOL_PROFILES.items()
    )

    try:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            invoke_json_prompt_chain,
            _RAG_ROUTER_PROMPT,
            {
                "tool_descriptions": tool_descriptions,
                "message": message,
            },
            generation_config={"temperature": 0, "max_output_tokens": 180, "response_mime_type": "application/json"},
            request_options={"timeout": 10},
            rotate=False,
        )
        try:
            payload, raw_text, used_model = future.result(timeout=4)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        primary_model = get_model()
        if primary_model is not None and used_model != primary_model.label:
            print(f"LLM router switched to fallback model: {used_model}")
        payload = payload or _extract_router_json(raw_text)
        if not payload:
            return None

        tool_name = str(payload.get("tool", "")).strip()
        try:
            confidence = float(payload.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0

        if tool_name == FALLBACK_RAG_NODE:
            return FALLBACK_RAG_NODE, f"router_llm:{confidence:.2f}"
        if tool_name in RAG_TOOL_PROFILES:
            if confidence < 0.25:
                return FALLBACK_RAG_NODE, f"router_llm_low_conf:{confidence:.2f}"
            return tool_name, f"router_llm:{tool_name}:{confidence:.2f}"
    except FutureTimeoutError:
        print("LLM router timed out, falling back to keyword routing.")
    except Exception as exc:
        print(f"LLM router unavailable, falling back to keyword routing: {exc}")

    return None


def route_rag_tool(message: str) -> tuple[str, str]:
    keyword_result = _route_rag_tool_by_keyword(message)
    if keyword_result[0] != FALLBACK_RAG_NODE and _keyword_route_score(keyword_result[1]) >= 6:
        return keyword_result

    llm_result = _route_rag_tool_by_llm(message)
    if llm_result is not None:
        return llm_result
    return keyword_result


def _normalize_retrieval_source(value: object) -> Optional[str]:
    source = str(value or "").strip().casefold()
    aliases = {
        "local": RETRIEVAL_LOCAL_DATA,
        "data": RETRIEVAL_LOCAL_DATA,
        "local_data": RETRIEVAL_LOCAL_DATA,
        "rag": RETRIEVAL_LOCAL_DATA,
        "vector": RETRIEVAL_LOCAL_DATA,
        "web": RETRIEVAL_WEB_SEARCH,
        "web_search": RETRIEVAL_WEB_SEARCH,
        "search": RETRIEVAL_WEB_SEARCH,
        "online": RETRIEVAL_WEB_SEARCH,
        "hybrid": RETRIEVAL_HYBRID,
        "both": RETRIEVAL_HYBRID,
        "local_and_web": RETRIEVAL_HYBRID,
    }
    return aliases.get(source)


def _normalize_retrieval_priority(value: object, source: str) -> str:
    priority = str(value or "").strip().casefold()
    if priority in {RETRIEVAL_LOCAL_FIRST, "local", "data", "rag"}:
        return RETRIEVAL_LOCAL_FIRST
    if priority in {RETRIEVAL_WEB_FIRST, "web", "search", "online"}:
        return RETRIEVAL_WEB_FIRST
    if source == RETRIEVAL_WEB_SEARCH:
        return RETRIEVAL_WEB_FIRST
    return RETRIEVAL_LOCAL_FIRST


def _fallback_retrieval_flow(message: str, *, route: str = "flow_keyword") -> RetrievalFlowPlan:
    if should_use_web_search(message):
        return RetrievalFlowPlan(
            source=RETRIEVAL_WEB_SEARCH,
            priority=RETRIEVAL_WEB_FIRST,
            reason="Cau hoi co dau hieu can thong tin moi/cap nhat.",
            confidence=0.55,
            route=f"{route}:web_search",
        )
    return RetrievalFlowPlan(
        source=RETRIEVAL_LOCAL_DATA,
        priority=RETRIEVAL_LOCAL_FIRST,
        reason="Mac dinh uu tien du lieu noi bo khi khong co dau hieu thoi gian thuc.",
        confidence=0.50,
        route=f"{route}:local_data",
    )


def _build_retrieval_flow_prompt(message: str, rag_tool: Optional[str]) -> str:
    tool_descriptions = "\n".join(
        f"- {tool_name}: {profile.get('description', profile.get('label', tool_name))}"
        for tool_name, profile in RAG_TOOL_PROFILES.items()
    )
    current_tool = rag_tool if rag_tool in RAG_TOOL_PROFILES else FALLBACK_RAG_NODE

    return f"""Ban la bo lap ke hoach truy xuat truoc khi chatbot tra loi.

Muc tieu:
- Quyet dinh cau hoi nen lay thong tin tu du lieu noi bo, web search ICTU, hay ket hop ca hai.
- Khong tra loi cau hoi cua nguoi dung.
- Chi tra ve JSON hop le, khong them giai thich ngoai JSON.

Nguon co the chon:
- local_data: dung corpus noi bo da nap, gom so tay sinh vien, quy dinh, FAQ, tai lieu upload va vector store.
- web_search: dung tim kiem web uu tien domain chinh thuc ICTU cho thong tin moi, thong bao, lich, tin tuc, tuyen sinh, deadline, so lieu/co cau co the thay doi.
- hybrid: lay local_data lam nen va bo sung web_search, hoac web_search truoc roi doi chieu local_data.

Nhom tri thuc RAG da duoc router goi y:
{current_tool}

Mo ta cac nhom tri thuc:
{tool_descriptions}

Quy tac quyet dinh:
- Chon local_data/local_first khi cau hoi hoi ve noi dung on dinh trong tai lieu da nap: so tay sinh vien, quy che, quy dinh, dieu kien, dinh nghia, quy trinh, cau hoi Q&A co san.
- Chon web_search/web_first khi cau hoi co dau hieu thoi gian thuc hoac can cap nhat: "hom nay", "moi nhat", "gan day", "nam nay", "thong bao moi", lich, deadline, tuyen sinh hien tai, chi tieu, hoc phi moi, tin tuc.
- Chon hybrid khi cau hoi can ca quy dinh nen trong tai lieu noi bo va tinh trang/thong bao moi tren website.
- Neu khong chac chan, uu tien local_data/local_first, tru khi cau hoi ro rang can thong tin moi.

JSON bat buoc:
{{
  "source": "local_data | web_search | hybrid",
  "priority": "local_first | web_first",
  "reason": "mot cau ngan noi ly do",
  "confidence": 0.0
}}

Cau hoi nguoi dung:
{message}
"""


def _route_retrieval_flow_by_llm(message: str, rag_tool: Optional[str]) -> Optional[RetrievalFlowPlan]:
    if get_model() is None or not _llm_router_network_available():
        return None

    tool_descriptions = "\n".join(
        f"- {tool_name}: {profile.get('description', profile.get('label', tool_name))}"
        for tool_name, profile in RAG_TOOL_PROFILES.items()
    )
    current_tool = rag_tool if rag_tool in RAG_TOOL_PROFILES else FALLBACK_RAG_NODE
    try:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            invoke_json_prompt_chain,
            _RETRIEVAL_FLOW_PROMPT,
            {
                "current_tool": current_tool,
                "tool_descriptions": tool_descriptions,
                "message": message,
            },
            generation_config={"temperature": 0, "max_output_tokens": 220, "response_mime_type": "application/json"},
            request_options={"timeout": 10},
            rotate=False,
        )
        try:
            payload, raw_text, used_model = future.result(timeout=4)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        primary_model = get_model()
        if primary_model is not None and used_model != primary_model.label:
            print(f"Retrieval flow planner switched to fallback model: {used_model}")

        payload = payload or _extract_router_json(raw_text)
        if not payload:
            return None

        source = _normalize_retrieval_source(payload.get("source"))
        if source is None:
            return None
        priority = _normalize_retrieval_priority(payload.get("priority"), source)
        try:
            confidence = float(payload.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        reason = str(payload.get("reason") or "").strip()[:240]

        if confidence < 0.25:
            return None

        return RetrievalFlowPlan(
            source=source,
            priority=priority,
            reason=reason or "LLM retrieval flow planner.",
            confidence=max(0.0, min(confidence, 1.0)),
            route=f"flow_llm:{source}:{priority}:{confidence:.2f}",
        )
    except FutureTimeoutError:
        print("Retrieval flow planner timed out, falling back to keyword flow.")
    except Exception as exc:
        print(f"Retrieval flow planner unavailable, falling back to keyword flow: {exc}")
    return None


def route_retrieval_flow(message: str, rag_tool: Optional[str] = None) -> RetrievalFlowPlan:
    llm_result = _route_retrieval_flow_by_llm(message, rag_tool)
    if llm_result is not None:
        return llm_result
    return _fallback_retrieval_flow(message)


def _plan_allows_web(plan: RetrievalFlowPlan) -> bool:
    return plan.source in {RETRIEVAL_WEB_SEARCH, RETRIEVAL_HYBRID}


def _plan_is_web_first(plan: RetrievalFlowPlan) -> bool:
    return plan.priority == RETRIEVAL_WEB_FIRST or plan.source == RETRIEVAL_WEB_SEARCH


def _build_planned_web_result(message: str, route_name: str, tool_name: Optional[str]) -> Optional[RAGResult]:
    return _build_web_knowledge_result(message, route_name=route_name, tool_name=tool_name) or _build_web_search_result(
        message,
        route_name=route_name,
        tool_name=tool_name,
    )


def retrieve_tool_context(
    message: str,
    session_id: str,
    tool_name: str,
    route_name: str,
    retrieval_plan: Optional[RetrievalFlowPlan] = None,
) -> RAGResult:
    scope_query = build_retrieval_query(session_id, message)
    if not is_ictu_related_query(scope_query):
        return _build_scope_guard_result(route_name=route_name, tool_name=tool_name)

    flow_plan = retrieval_plan or route_retrieval_flow(scope_query, tool_name)
    planned_route_name = f"{route_name}|{flow_plan.route}"
    web_result: Optional[RAGResult] = None

    if _plan_allows_web(flow_plan) and _plan_is_web_first(flow_plan):
        web_result = _build_planned_web_result(scope_query, route_name=planned_route_name, tool_name=tool_name)
        if web_result is not None and flow_plan.source == RETRIEVAL_WEB_SEARCH:
            return web_result

    lexical_documents = CorpusLexicalRetriever(
        document_supplier=lambda: _load_tool_corpus(tool_name),
        search_fn=_search_documents,
        snippet_fn=_extract_relevant_snippet,
        tool_name=tool_name,
        limit=4,
    ).invoke(message)

    if not lexical_documents:
        if web_result is not None:
            return web_result
        if _plan_allows_web(flow_plan):
            web_result = _build_planned_web_result(scope_query, route_name=planned_route_name, tool_name=tool_name)
            if web_result is not None:
                return web_result
        return retrieve_general_context(
            message,
            session_id,
            route_name=planned_route_name,
            tool_name=tool_name,
            retrieval_plan=flow_plan,
        )

    inject_bot_rule(force_full=True)
    result = _build_result_from_documents(
        documents=lexical_documents,
        tool_name=tool_name,
        route_name=planned_route_name,
        mode=tool_name,
    )

    if flow_plan.source == RETRIEVAL_WEB_SEARCH:
        web_result = web_result or _build_planned_web_result(scope_query, route_name=planned_route_name, tool_name=tool_name)
        return web_result or result

    if flow_plan.source == RETRIEVAL_HYBRID:
        web_result = web_result or _build_planned_web_result(scope_query, route_name=planned_route_name, tool_name=tool_name)
        return _merge_web_search_result(
            result,
            web_result,
            web_first=_plan_is_web_first(flow_plan),
        )

    return result



def retrieve_fallback_context(
    message: str,
    session_id: str,
    route_name: str = "router_fallback",
    retrieval_plan: Optional[RetrievalFlowPlan] = None,
) -> RAGResult:
    scope_query = build_retrieval_query(session_id, message)
    if not is_ictu_related_query(scope_query):
        return _build_scope_guard_result(route_name=route_name, tool_name=FALLBACK_RAG_NODE)

    flow_plan = retrieval_plan or route_retrieval_flow(scope_query, FALLBACK_RAG_NODE)
    planned_route_name = f"{route_name}|{flow_plan.route}"
    web_result: Optional[RAGResult] = None

    if _plan_allows_web(flow_plan) and _plan_is_web_first(flow_plan):
        web_result = _build_planned_web_result(scope_query, route_name=planned_route_name, tool_name=FALLBACK_RAG_NODE)
        if web_result is not None and flow_plan.source == RETRIEVAL_WEB_SEARCH:
            return web_result

    def _fallback_search(_: tuple[CorpusDocument, ...], query: str, limit: int = 6) -> list[tuple[int, CorpusDocument]]:
        all_matches: list[tuple[int, CorpusDocument]] = []
        for tool in RAG_TOOL_ORDER:
            documents = _load_tool_corpus(tool)
            all_matches.extend(_search_documents(documents, query, limit=2))
        all_matches.sort(key=lambda item: item[0], reverse=True)
        return all_matches[:limit]

    fallback_documents = CorpusLexicalRetriever(
        document_supplier=_load_all_tool_documents,
        search_fn=_fallback_search,
        snippet_fn=_extract_relevant_snippet,
        tool_name=FALLBACK_RAG_NODE,
        limit=6,
    ).invoke(message)

    if not fallback_documents:
        if web_result is not None:
            return web_result
        if _plan_allows_web(flow_plan):
            web_result = _build_planned_web_result(scope_query, route_name=planned_route_name, tool_name=FALLBACK_RAG_NODE)
            if web_result is not None:
                return web_result
        return retrieve_general_context(
            message,
            session_id,
            route_name=planned_route_name,
            tool_name=DEFAULT_RAG_TOOL,
            retrieval_plan=flow_plan,
        )

    inject_bot_rule(force_full=True)
    result = _build_result_from_documents(
        documents=fallback_documents,
        tool_name=FALLBACK_RAG_NODE,
        route_name=planned_route_name,
        mode="multi_tool_fallback_rag",
    )

    if flow_plan.source == RETRIEVAL_WEB_SEARCH:
        web_result = web_result or _build_planned_web_result(scope_query, route_name=planned_route_name, tool_name=FALLBACK_RAG_NODE)
        return web_result or result

    if flow_plan.source == RETRIEVAL_HYBRID:
        web_result = web_result or _build_planned_web_result(scope_query, route_name=planned_route_name, tool_name=FALLBACK_RAG_NODE)
        return _merge_web_search_result(
            result,
            web_result,
            web_first=_plan_is_web_first(flow_plan),
        )

    return result



def detect_target_file(message_lower: str, documents: Optional[tuple[CorpusDocument, ...]] = None) -> Optional[str]:
    pool = documents if documents is not None else _load_all_tool_documents()
    for doc in pool:
        name = doc.path.stem.casefold()
        variants = [name, name.replace("-", " "), doc.source.casefold()]
        if any(variant in message_lower for variant in variants if len(variant) > 2):
            return doc.source
    return None



def _detect_collection_source(message_lower: str) -> Optional[str]:
    try:
        coll = get_collection()
        data = coll.get(include=["metadatas"])
    except Exception as exc:
        print(f"Vector source detection unavailable: {exc}")
        return None

    all_sources = {m.get("source", "") for m in data.get("metadatas", []) if m}

    for src in all_sources:
        if src == "BOT_RULE":
            continue
        name = src.lower().replace(".md", "").replace(".markdown", "")
        variants = [name, name.replace("-", " "), f"file {name}", f"trong {name}"]
        if any(variant in message_lower for variant in variants if len(variant) > 2):
            return src
    return None



def build_retrieval_query(session_id: str, message: str) -> str:
    history = SESSION_MEMORY[session_id]
    if history:
        previous_q = history[-1]["query"]
        return f"{previous_q} {message}"
    return message



def _build_scope_guard_result(route_name: str, tool_name: Optional[str]) -> RAGResult:
    return RAGResult(
        context_text=ICTU_SCOPE_REPLY_VI,
        chunks=[],
        target_file=None,
        mode="ictu_scope_guard",
        sources=[],
        chunks_used=0,
        rag_tool=tool_name,
        rag_route=route_name,
    )



def build_context_from_chunks(chunks: list[RetrievedChunk], max_chunks: int = 25) -> tuple[str, list[str]]:
    context_parts: list[str] = []
    sources: list[str] = []

    for chunk in chunks[:max_chunks]:
        title = chunk.metadata.get("title", "").strip()
        text = chunk.document.strip().replace("\n", " ")[:2000]
        source = chunk.metadata.get("source", "")

        if source and source != "BOT_RULE":
            sources.append(source)

        if title and title != "Khong co tieu de":
            context_parts.append(f"[{title}]\n{text}")
        else:
            context_parts.append(text)

    context_text = "\n\n".join(context_parts) if context_parts else "Thong tin dang duoc cap nhat."
    return context_text, sources



def _build_general_fallback_result(
    message: str,
    route_name: str,
    tool_name: Optional[str],
    retrieval_plan: Optional[RetrievalFlowPlan] = None,
) -> RAGResult:
    flow_plan = retrieval_plan or route_retrieval_flow(message, tool_name)
    web_result: Optional[RAGResult] = None

    if _plan_allows_web(flow_plan) and _plan_is_web_first(flow_plan):
        web_result = _build_planned_web_result(message, route_name=route_name, tool_name=tool_name)
        if web_result is not None and flow_plan.source == RETRIEVAL_WEB_SEARCH:
            return web_result

    fallback_documents = CorpusLexicalRetriever(
        document_supplier=_load_all_tool_documents,
        search_fn=_search_documents,
        snippet_fn=_extract_relevant_snippet,
        tool_name=tool_name or FALLBACK_RAG_NODE,
        limit=6,
    ).invoke(message)
    if fallback_documents:
        result = _build_result_from_documents(
            documents=fallback_documents,
            tool_name=tool_name or FALLBACK_RAG_NODE,
            route_name=route_name,
            mode="lexical_fallback",
        )

        if flow_plan.source == RETRIEVAL_WEB_SEARCH:
            web_result = web_result or _build_planned_web_result(message, route_name=route_name, tool_name=tool_name)
            return web_result or result

        if flow_plan.source == RETRIEVAL_HYBRID:
            web_result = web_result or _build_planned_web_result(message, route_name=route_name, tool_name=tool_name)
            return _merge_web_search_result(
                result,
                web_result,
                web_first=_plan_is_web_first(flow_plan),
            )

        return result

    result = RAGResult(
        context_text="Thong tin dang duoc cap nhat.",
        chunks=[],
        target_file=None,
        mode="lexical_fallback_empty",
        sources=[],
        chunks_used=0,
        rag_tool=tool_name,
        rag_route=route_name,
    )

    if _plan_allows_web(flow_plan):
        return _merge_web_search_result(
            result,
            web_result or _build_planned_web_result(message, route_name=route_name, tool_name=tool_name),
            web_first=_plan_is_web_first(flow_plan),
        )
    return result



def retrieve_general_context(
    message: str,
    session_id: str,
    route_name: str = "general_fallback",
    tool_name: Optional[str] = None,
    retrieval_plan: Optional[RetrievalFlowPlan] = None,
) -> RAGResult:
    query_for_retrieval = build_retrieval_query(session_id, message)
    if not is_ictu_related_query(query_for_retrieval):
        return _build_scope_guard_result(route_name=route_name, tool_name=tool_name)

    flow_plan = retrieval_plan or route_retrieval_flow(query_for_retrieval, tool_name)
    planned_route_name = route_name if f"|{flow_plan.route}" in route_name else f"{route_name}|{flow_plan.route}"
    web_result: Optional[RAGResult] = None

    if _plan_allows_web(flow_plan) and _plan_is_web_first(flow_plan):
        web_result = _build_planned_web_result(query_for_retrieval, route_name=planned_route_name, tool_name=tool_name)
        if web_result is not None and flow_plan.source == RETRIEVAL_WEB_SEARCH:
            return web_result

    message_lower = message.lower()
    target_file = None

    if not embedding_backend_ready():
        return _build_general_fallback_result(message, planned_route_name, tool_name, retrieval_plan=flow_plan)

    try:
        target_file = _detect_collection_source(message_lower)
        documents = VectorStoreRetriever(
            query_fn=query_documents,
            collection_getter=get_collection,
            user_id=session_id,
            n_results=100,
            alpha=0.7,
            target_source=target_file,
        ).invoke(query_for_retrieval)
        mode = "forced_file" if target_file else "hybrid_search"
    except Exception as exc:
        print(f"Vector retrieval unavailable, using lexical fallback: {exc}")
        return _build_general_fallback_result(message, planned_route_name, tool_name, retrieval_plan=flow_plan)

    inject_bot_rule(force_full=True)
    result = _build_result_from_documents(
        documents=documents,
        tool_name=tool_name,
        route_name=planned_route_name,
        mode=mode,
        target_file=target_file,
        context_max_chunks=25,
    )
    unique_sources = result.sources

    if flow_plan.source == RETRIEVAL_WEB_SEARCH:
        web_result = web_result or _build_planned_web_result(query_for_retrieval, route_name=planned_route_name, tool_name=tool_name)
        return web_result or result

    if flow_plan.source == RETRIEVAL_HYBRID or (not unique_sources and _plan_allows_web(flow_plan)):
        web_result = web_result or _build_planned_web_result(query_for_retrieval, route_name=planned_route_name, tool_name=tool_name)
        return _merge_web_search_result(
            result,
            web_result,
            web_first=_plan_is_web_first(flow_plan),
        )

    return result



def retrieve_context(message: str, session_id: str) -> RAGResult:
    return retrieve_general_context(message, session_id)






