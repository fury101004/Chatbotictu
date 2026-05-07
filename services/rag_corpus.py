from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional
import re

from config.rag_tools import QA_ROOT, RAG_TOOL_ORDER, RAG_UPLOAD_ROOT, get_tool_corpus_paths
from shared.text_utils import normalize_search_text, tokenize_search_text

from services.rag_types import CorpusDocument

_COHORT_RE = re.compile(r"\b(?:k|khoa)\s*0*([1-9][0-9])\b")
_YEAR_RE = re.compile(r"\b(20[0-9]{2})\b")
_YEAR_RANGE_RE = re.compile(r"\b(20[0-9]{2})\s*[-/]\s*(20[0-9]{2})\b")


def _normalize_for_match(text: str) -> str:
    return normalize_search_text(text)



def _tokenize(text: str) -> list[str]:
    return tokenize_search_text(text)



def _extract_cohort_tags(text: str) -> frozenset[str]:
    tags = {f"k{int(match.group(1)):02d}" for match in _COHORT_RE.finditer(text)}
    return frozenset(tags)


def _extract_year_values(text: str) -> frozenset[int]:
    return frozenset(int(match.group(1)) for match in _YEAR_RE.finditer(text))


def _extract_year_ranges(text: str) -> frozenset[str]:
    ranges: set[str] = set()
    for match in _YEAR_RANGE_RE.finditer(text):
        start = match.group(1)
        end = match.group(2)
        ranges.add(f"{start}-{end}")
    return frozenset(ranges)


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
            cohort_tags = _extract_cohort_tags(
                f"{normalized_title}\n{normalized_source}\n{normalized_text}"
            )
            year_values = _extract_year_values(
                f"{normalized_title}\n{normalized_source}\n{normalized_text}"
            )
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
                    cohort_tags=cohort_tags,
                    year_values=year_values,
                    max_year=max(year_values, default=0),
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


def _is_program_credit_query(query_tokens: list[str], query_phrases: list[str]) -> bool:
    token_set = set(query_tokens)
    has_program_terms = (
        ("chuong" in token_set and "trinh" in token_set)
        or ("dao" in token_set and "tao" in token_set)
        or "ctdt" in token_set
    )
    has_credit_terms = "tin" in token_set and "chi" in token_set
    has_program_phrase = any(
        phrase in {"chuong trinh hoc", "chuong trinh dao tao", "tong so tin chi", "bao nhieu tin chi"}
        for phrase in query_phrases
    )
    return has_program_terms or has_credit_terms or has_program_phrase


def _score_document(
    doc: CorpusDocument,
    query_tokens: list[str],
    query_phrases: list[str],
    *,
    query_cohorts: frozenset[str],
    query_years: frozenset[int],
    prefer_recent: bool,
) -> int:
    if not query_tokens:
        return 0

    unique_tokens = set(query_tokens)
    phrase_set = set(query_phrases)
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
    year_overlap = len(query_years & doc.year_values) if query_years else 0
    year_bonus = 0
    if year_overlap > 0:
        year_bonus = 10 + year_overlap * 3
    elif query_years:
        year_bonus = -4

    cohort_overlap = len(query_cohorts & doc.cohort_tags) if query_cohorts else 0
    cohort_bonus = 0
    if cohort_overlap > 0:
        cohort_bonus = 24 + cohort_overlap * 8
    elif query_cohorts:
        cohort_bonus = -8

    recency_bonus = 0
    if prefer_recent and doc.max_year > 0:
        recency_bonus = max(0, min(14, doc.max_year - 2018))

    program_bonus = 0
    if prefer_recent and (
        "chuong trinh dao tao" in doc.normalized_text
        or "tong so tin chi" in doc.normalized_text
        or "tai ve" in doc.normalized_text
    ):
        program_bonus = 8

    wants_total_credit = (
        "tong so tin chi" in phrase_set
        or (
            {"bao", "nhieu", "tin", "chi"}.issubset(unique_tokens)
            and ({"chuong", "trinh"}.issubset(unique_tokens) or "ctdt" in unique_tokens)
        )
    )
    total_credit_bonus = 0
    if wants_total_credit:
        if "tong so tin chi" in doc.normalized_text:
            total_credit_bonus = 20
        elif doc.path.name.casefold().endswith(".questions.md"):
            total_credit_bonus = -22

    ctdt_sheet_bonus = 0
    if wants_total_credit and (
        "ctdt_sheet_import" in doc.normalized_text
        or doc.source.startswith("uploads/student_handbook_rag/ctdt_")
    ):
        ctdt_sheet_bonus = 24

    questions_penalty = 0
    if (
        prefer_recent
        and doc.path.name.casefold().endswith(".questions.md")
        and cohort_overlap == 0
        and year_overlap == 0
    ):
        questions_penalty = -6

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
        + cohort_bonus
        + recency_bonus
        + program_bonus
        + total_credit_bonus
        + ctdt_sheet_bonus
        + questions_penalty
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

    normalized_query = _normalize_for_match(message)
    line_pairs = [(line, _normalize_for_match(line)) for line in lines]
    matched_lines = [line for line, normalized in line_pairs if any(token in normalized for token in query_tokens)]

    token_set = set(query_tokens)
    asks_total_credit = (
        ("tong" in token_set and "tin" in token_set and "chi" in token_set)
        or "bao nhieu tin chi" in normalized_query
        or "tong so tin chi" in normalized_query
    )

    if asks_total_credit:
        credit_priority_lines = [
            line
            for line, normalized in line_pairs
            if "tong so tin chi" in normalized
            or "tong so tc" in normalized
            or "tin chi tich luy" in normalized
        ]
        selected_lines = (credit_priority_lines + matched_lines)[:12] if credit_priority_lines else (
            matched_lines[:10] if matched_lines else lines[:12]
        )
    else:
        selected_lines = matched_lines[:10] if matched_lines else lines[:12]

    snippet = "\n".join(selected_lines).strip()
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars].rstrip()
    return snippet


def _search_documents(documents: tuple[CorpusDocument, ...], message: str, limit: int = 4) -> list[tuple[int, CorpusDocument]]:
    normalized_message = _normalize_for_match(message)
    query_tokens = _tokenize(normalized_message)
    query_phrases = _candidate_phrases(message)
    query_cohorts = _extract_cohort_tags(normalized_message)
    query_year_ranges = _extract_year_ranges(normalized_message)
    query_years = frozenset(
        int(token)
        for token in query_tokens
        if token.isdigit() and len(token) == 4 and token.startswith("20")
    )
    prefer_recent = _is_program_credit_query(query_tokens, query_phrases)

    scored = [
        (score, doc)
        for doc in documents
        if (
            score := _score_document(
                doc,
                query_tokens,
                query_phrases,
                query_cohorts=query_cohorts,
                query_years=query_years,
                prefer_recent=prefer_recent,
            )
        ) > 0
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        return []

    if query_year_ranges:
        year_range_filtered = [
            item
            for item in scored
            if any(
                year_range in item[1].normalized_source
                or year_range in item[1].normalized_title
                or year_range in item[1].normalized_text
                for year_range in query_year_ranges
            )
        ]
        if year_range_filtered:
            scored = year_range_filtered

    top_score = scored[0][0]
    threshold = max(8, top_score - 12, int(top_score * 0.6))
    filtered = [item for item in scored if item[0] >= threshold]
    return filtered[:limit]


def detect_target_file(message_lower: str, documents: Optional[tuple[CorpusDocument, ...]] = None) -> Optional[str]:
    pool = documents if documents is not None else _load_all_tool_documents()
    for doc in pool:
        name = doc.path.stem.casefold()
        variants = [name, name.replace("-", " "), doc.source.casefold()]
        if any(variant in message_lower for variant in variants if len(variant) > 2):
            return doc.source
    return None

