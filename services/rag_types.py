from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
    cohort_tags: frozenset[str] = frozenset()
    year_values: frozenset[int] = frozenset()
    max_year: int = 0


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
