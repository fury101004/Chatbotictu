"""RAG service with 3 route-specific agents: handbook, policy and faq."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Sequence

from langchain.prompts import PromptTemplate
from langchain.schema import Document
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from app.data.pipeline import ROUTE_LABELS, get_multi_retriever, infer_route_from_metadata
from app.services.llm_service import invoke_llm
from app.services.reranker import rerank


AVAILABLE_ROUTES = ("handbook", "policy", "faq")
FAQ_HINTS = (
    "email",
    "mail",
    "bhyt",
    "bao hiem",
    "hoc bong",
    "hoc phi",
    "mien giam",
    "tro cap",
    "tot nghiep",
    "diem ren luyen",
    "the sinh vien",
    "ho so",
    "viec lam",
)
HANDBOOK_HINTS = (
    "so tay",
    "cam nang",
    "dang ky hoc",
    "huy hoc phan",
    "phuc khao",
    "lich thi",
    "chuong trinh dao tao",
    "dau moi lien he",
)

AGENT_INSTRUCTIONS = {
    "handbook": (
        "Ban la Agent So tay sinh vien. "
        "Uu tien cach tra loi co tinh huong dan, tong hop, de sinh vien lam theo tung buoc."
    ),
    "policy": (
        "Ban la Agent Chinh sach - Cong van - Quyet dinh. "
        "Uu tien neu ro ten van ban, nam hoc, hoc ky, so hieu neu du lieu co."
    ),
    "faq": (
        "Ban la Agent Cau hoi sinh vien thuong dung. "
        "Tra loi ngan gon, de hieu, sau do neu can thi dinh huong sang van ban chinh thuc."
    ),
}

ROUTE_PROMPT = PromptTemplate.from_template(
    """
Ban dang la bo dieu phoi 3 agent cho chatbot sinh vien.

Hay chon DUY NHAT mot agent phu hop nhat:
- handbook: dung khi cau hoi can tra cuu so tay sinh vien, huong dan tong quan, dau moi lien he, quy trinh hoc vu co ban.
- policy: dung khi cau hoi can can cu cong van, thong bao, quyet dinh, quy dinh, chinh sach, van ban chinh thuc.
- faq: dung khi cau hoi la van de sinh vien thuong hoi hang ngay nhu email, BHYT, hoc bong, hoc phi, tot nghiep, diem ren luyen, thu tuc.

Chi tra ve duy nhat mot tu trong ba tu: handbook, policy, faq.

Cau hoi: {question}
"""
)

ANSWER_PROMPT = PromptTemplate.from_template(
    """
{agent_instruction}

Nguyen tac tra loi:
- Chi duoc dua tren NGU LIEU.
- Neu tai lieu co nam hoc, hoc ky, so van ban, ten van ban thi uu tien neu ro.
- Neu chua du du lieu thi noi ro phan chua chac va goi y nguoi dung bo sung thong tin.
- Tra loi bang tieng Viet, ro rang, ngan gon, tranh doan van qua dai.
- Neu can huong dan thao tac, viet thanh tung dong de sinh vien de lam theo.

LICH SU GAN DAY:
{memory}

NGU LIEU:
{context}

CAU HOI:
{question}
"""
)


class ChatState(TypedDict):
    question: str
    history: List[Dict[str, Any]]
    memory: str
    route: str
    documents: List[Document]
    context: str
    answer: str
    sources: List[str]


def _normalize_lookup_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_route(value: str) -> str:
    cleaned = _normalize_lookup_text(value)
    if not cleaned:
        return ""

    first_line = cleaned.splitlines()[0]
    first_token = first_line.split(" ")[0] if first_line else ""
    token = re.sub(r"[^a-z]", "", first_token)
    return token if token in AVAILABLE_ROUTES else ""


def _heuristic_route(question: str) -> str:
    normalized = _normalize_lookup_text(question)

    if any(keyword in normalized for keyword in HANDBOOK_HINTS):
        return "handbook"

    if any(keyword in normalized for keyword in FAQ_HINTS):
        return "faq"

    if any(keyword in normalized for keyword in ("quyet dinh", "cong van", "thong bao", "quy dinh", "chinh sach")):
        return "policy"

    if len(normalized.split()) <= 8 and any(
        normalized.startswith(prefix)
        for prefix in ("lam sao", "khi nao", "o dau", "nhu the nao", "co can", "em can")
    ):
        return "faq"

    return "policy"


def _build_memory(history: Sequence[Dict[str, Any]], limit: int = 5) -> str:
    if not history:
        return "Khong co lich su truoc do."

    snippets: List[str] = []
    for item in history[-limit:]:
        snippets.append(f"User: {item['question']}")
        snippets.append(f"Bot: {item['answer']}")

    return "\n".join(snippets)


def _available_retrievers() -> Dict[str, Any]:
    return get_multi_retriever()


def _invoke_retriever(retriever: Any, question: str) -> List[Document]:
    if retriever is None:
        return []

    if hasattr(retriever, "invoke"):
        return list(retriever.invoke(question))

    if hasattr(retriever, "get_relevant_documents"):
        return list(retriever.get_relevant_documents(question))

    return []


def _document_key(document: Document) -> str:
    source = str(
        document.metadata.get("source")
        or document.metadata.get("source_file")
        or document.metadata.get("source_md")
        or document.metadata.get("title")
        or "unknown"
    )
    preview = re.sub(r"\s+", " ", document.page_content[:180]).strip()
    return f"{source}::{preview}"


def _deduplicate_documents(documents: Sequence[Document]) -> List[Document]:
    deduplicated: List[Document] = []
    seen = set()

    for document in documents:
        key = _document_key(document)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(document)

    return deduplicated


def _preferred_documents_for_route(documents: Sequence[Document], route: str) -> List[Document]:
    preferred: List[Document] = []
    fallback: List[Document] = []

    for document in documents:
        inferred = infer_route_from_metadata(document.metadata)
        if inferred == route:
            preferred.append(document)
        else:
            fallback.append(document)

    if route == "faq":
        return preferred + fallback

    return preferred or fallback


def _limit_per_source(documents: Sequence[Document], max_per_source: int) -> List[Document]:
    counts: Dict[str, int] = {}
    limited: List[Document] = []

    for document in documents:
        source = str(
            document.metadata.get("source")
            or document.metadata.get("source_file")
            or document.metadata.get("source_md")
            or "unknown"
        )
        current = counts.get(source, 0)
        if current >= max_per_source:
            continue
        counts[source] = current + 1
        limited.append(document)

    return limited


def _retrieve_for_route(retrievers: Dict[str, Any], route: str, question: str) -> List[Document]:
    if route == "handbook":
        documents = _invoke_retriever(retrievers.get("handbook"), question)
        if len(documents) < 4:
            documents.extend(_invoke_retriever(retrievers.get("policy"), question))
        return documents

    if route == "faq":
        documents = _invoke_retriever(retrievers.get("faq"), question)
        documents.extend(_invoke_retriever(retrievers.get("policy"), question))
        if len(documents) < 4:
            documents.extend(_invoke_retriever(retrievers.get("handbook"), question))
        return documents

    documents = _invoke_retriever(retrievers.get("policy"), question)
    if len(documents) < 4:
        documents.extend(_invoke_retriever(retrievers.get("handbook"), question))
    return documents


def _build_context(documents: Sequence[Document], limit: int = 5) -> Dict[str, Any]:
    selected_documents = list(documents)[:limit]
    context_blocks: List[str] = []
    sources: List[str] = []
    seen_sources = set()

    for index, document in enumerate(selected_documents, start=1):
        source = str(document.metadata.get("source", "unknown"))
        title = str(document.metadata.get("title") or Path(source).stem or f"document-{index}")
        year = str(document.metadata.get("year", ""))
        route = str(document.metadata.get("route", infer_route_from_metadata(document.metadata)))
        preview = document.page_content.strip()[:1000]

        header = f"[{index}] {title}"
        if year:
            header += f" | Nam: {year}"
        header += f" | Route: {route}"
        context_blocks.append(f"{header}\nSource: {source}\n{preview}")
        if source not in seen_sources:
            sources.append(source)
            seen_sources.add(source)

    return {
        "context": "\n\n".join(context_blocks).strip(),
        "sources": sources,
    }


def memory_node(state: ChatState) -> ChatState:
    return {
        **state,
        "memory": _build_memory(state["history"]),
    }


def route_node(state: ChatState) -> ChatState:
    try:
        route_response = invoke_llm(ROUTE_PROMPT.format(question=state["question"]))
    except Exception:
        route_response = ""

    route = _normalize_route(route_response) or _heuristic_route(state["question"])
    return {
        **state,
        "route": route,
    }


def retrieve_node(state: ChatState) -> ChatState:
    retrievers = _available_retrievers()
    route = state["route"]

    raw_documents = _retrieve_for_route(retrievers, route, state["question"])
    deduplicated = _deduplicate_documents(raw_documents)
    preferred = _preferred_documents_for_route(deduplicated, route)
    ranked_documents = rerank(state["question"], preferred, top_k=6)
    if route == "faq":
        ranked_documents = _limit_per_source(ranked_documents, max_per_source=1)
    else:
        ranked_documents = _limit_per_source(ranked_documents, max_per_source=2)
    context_payload = _build_context(ranked_documents)

    return {
        **state,
        "documents": ranked_documents,
        "context": context_payload["context"],
        "sources": context_payload["sources"],
    }


def answer_node(state: ChatState) -> ChatState:
    if not state["context"]:
        answer = (
            "Minh chua tim thay tai lieu phu hop trong kho du lieu hien tai. "
            "Ban co the noi ro hon nam hoc, hoc ky, so van ban hoac chu de can tra cuu khong?"
        )
        return {
            **state,
            "answer": answer,
        }

    prompt = ANSWER_PROMPT.format(
        agent_instruction=AGENT_INSTRUCTIONS.get(state["route"], AGENT_INSTRUCTIONS["policy"]),
        memory=state["memory"],
        context=state["context"],
        question=state["question"],
    )

    try:
        answer = invoke_llm(prompt).strip()
    except Exception:
        answer = (
            "Minh khong the goi mo hinh tra loi luc nay. "
            "Ban thu lai sau hoac kiem tra ket noi Ollama giup minh."
        )

    return {
        **state,
        "answer": answer,
    }


def _build_graph():
    builder = StateGraph(ChatState)
    builder.add_node("memory", memory_node)
    builder.add_node("route", route_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("answer", answer_node)

    builder.set_entry_point("memory")
    builder.add_edge("memory", "route")
    builder.add_edge("route", "retrieve")
    builder.add_edge("retrieve", "answer")
    builder.add_edge("answer", END)

    return builder.compile()


chat_graph = _build_graph()


def rag_chat(question: str, history: List[Dict[str, Any]]) -> Dict[str, Any]:
    state: ChatState = {
        "question": question,
        "history": history,
        "memory": "",
        "route": "policy",
        "documents": [],
        "context": "",
        "answer": "",
        "sources": [],
    }

    result = chat_graph.invoke(state)
    route = result["route"]
    return {
        "answer": result["answer"],
        "route": route,
        "agent": route,
        "agent_label": ROUTE_LABELS.get(route, route),
        "sources": result["sources"],
    }
