from __future__ import annotations

from typing import Any, Optional

from langchain_core.callbacks.manager import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field

from shared.text_utils import tokenize_search_text


class CorpusLexicalRetriever(BaseRetriever):
    document_supplier: Any = Field(exclude=True)
    search_fn: Any = Field(exclude=True)
    snippet_fn: Any = Field(exclude=True)
    tool_name: str
    limit: int = 4

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        del run_manager
        documents = self.document_supplier()
        matches = self.search_fn(documents, query, limit=self.limit)
        results: list[Document] = []

        for score, doc in matches:
            snippet = self.snippet_fn(doc, query, self._tokenize(query))
            results.append(
                Document(
                    page_content=snippet,
                    metadata={
                        "source": doc.source,
                        "title": doc.title,
                        "score": score,
                        "tool_name": self.tool_name,
                        "path": str(doc.path),
                        "context_entry": f"[{doc.title} | source: {doc.source} | score: {score}]\n{snippet}",
                    },
                )
            )

        return results

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return tokenize_search_text(text)


class VectorStoreRetriever(BaseRetriever):
    query_fn: Any = Field(exclude=True)
    collection_getter: Any = Field(exclude=True)
    source_lookup_fn: Any = Field(default=None, exclude=True)
    user_id: str = "default"
    n_results: int = 100
    alpha: float = 0.7
    target_source: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        del run_manager

        if self.target_source:
            if self.source_lookup_fn is not None:
                documents, metadatas = self.source_lookup_fn(self.target_source)
            else:
                collection = self.collection_getter()
                data = collection.get(where={"source": self.target_source}, include=["documents", "metadatas"])
                documents = data.get("documents", [])
                metadatas = data.get("metadatas", [])
        else:
            documents, metadatas, _ = self.query_fn(
                query,
                user_id=self.user_id,
                n_results=self.n_results,
                alpha=self.alpha,
            )

        return [
            Document(page_content=str(document or ""), metadata=dict(metadata or {}))
            for document, metadata in zip(documents, metadatas)
        ]


class WebKnowledgeRetriever(BaseRetriever):
    search_fn: Any = Field(exclude=True)
    tool_name: str
    limit: int = 4

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        del run_manager
        matches = self.search_fn(query, limit=self.limit)
        documents: list[Document] = []

        for match in matches:
            source_label = ", ".join(match.sources) if match.sources else "web_knowledge_base"
            documents.append(
                Document(
                    page_content=match.answer,
                    metadata={
                        "source": source_label,
                        "title": match.question,
                        "score": match.score,
                        "source_type": "web_knowledge",
                        "web_knowledge_id": match.entry_id,
                        "expires_at": match.expires_at,
                        "tool_name": self.tool_name,
                        "context_entry": (
                            f"[Trusted web KB | question: {match.question} | score: {match.score} | source: {source_label}]\n"
                            f"{match.answer}\n\nNguồn tham khảo:\n{match.source_text[:1600]}"
                        ),
                        "sources": list(match.sources),
                    },
                )
            )

        return documents


class WebSearchRetriever(BaseRetriever):
    search_fn: Any = Field(exclude=True)
    tool_name: str
    limit: int = 4

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        del run_manager
        web_docs = self.search_fn(query, limit=self.limit)
        documents: list[Document] = []

        for doc in web_docs:
            documents.append(
                Document(
                    page_content=doc.text,
                    metadata={
                        "source": doc.url,
                        "title": doc.title,
                        "snippet": doc.snippet,
                        "source_type": "web_search",
                        "tool_name": self.tool_name,
                        "context_entry": f"[Web search ICTU | title: {doc.title} | source: {doc.url}]\n{doc.text}",
                    },
                )
            )

        return documents
