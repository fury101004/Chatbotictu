from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from services.rag.ictu_scope_service import is_ictu_related_query, normalize_scope_text


WEB_SEARCH_RESULT_LIMIT = 4
WEB_EXTRACT_RESULT_LIMIT = 2
SEARCH_TIMEOUT_SECONDS = 10.0
EXTRACT_TIMEOUT_SECONDS = 16.0

REALTIME_MARKERS = (
    "hôm nay",
    "mới nhất",
    "gần đây",
    "cập nhật",
    "tin mới",
    "tin tức",
    "năm nay",
    "tuyển sinh",
    "lịch",
    "thông báo mới",
    # Hỏi tin / thông báo động (thường không có trong corpus tĩnh)
    "có thông báo",
    "thông báo gì",
    "thông báo nào",
    "thông báo không",
    "tin chính thức",
)
NORMALIZED_REALTIME_MARKERS = tuple(normalize_scope_text(marker) for marker in REALTIME_MARKERS)

# Sau normalize_scope_text, ngày dạng 13/5/2026 thành "13 5 2026" (khoảng trắng).
_DATED_THONG_BAO_RE = re.compile(
    r"(?:\d{1,2}\s+\d{1,2}\s+20\d{2}.+thong\s+bao|thong\s+bao.+\d{1,2}\s+\d{1,2}\s+20\d{2})",
    re.IGNORECASE,
)

ICTU_WEB_QUERY_MARKER = '"Trường Đại học Công nghệ Thông tin và Truyền thông Thái Nguyên" ICTU'
ICTU_OFFICIAL_DOMAIN = "ictu.edu.vn"
ICTU_DOMAINS = ("ictu.edu.vn", "ictu.vn")
ICTU_QUERY_MARKERS = (
    "ictu",
    "Đại học Công nghệ Thông tin và Truyền thông",
    "Trường Đại học Công nghệ Thông tin và Truyền thông",
)
NORMALIZED_ICTU_QUERY_MARKERS = tuple(normalize_scope_text(marker) for marker in ICTU_QUERY_MARKERS)


@dataclass(slots=True)
class WebSearchDocument:
    title: str
    url: str
    snippet: str
    text: str


def _clean_base_url(value: str) -> str:
    return value.strip().rstrip("/")


def _search_base_url() -> str:
    return _clean_base_url(
        os.getenv("SEARXNG_URL", "")
        or os.getenv("SEARXNG_API", "")
        or os.getenv("SEAXNG_API", "")
    )


def _extract_base_url() -> str:
    return _clean_base_url(os.getenv("TRAFILATURA_URL", "") or os.getenv("TRAFILATURA_API", ""))


def web_search_configured() -> bool:
    return bool(_search_base_url())


def should_use_web_search(query: str) -> bool:
    normalized = normalize_scope_text(query or "")
    if any(marker in normalized for marker in NORMALIZED_REALTIME_MARKERS):
        return True
    # Câu hỏi gắn ngày cụ thể + "thông báo" (vd: ngày 13/5/2026 có thông báo gì) — cần web, không chỉ RAG tĩnh.
    if "thong bao" in normalized and _DATED_THONG_BAO_RE.search(normalized):
        return True
    return False


def _with_search_path(base_url: str) -> str:
    return base_url if base_url.endswith("/search") else f"{base_url}/search"


def _with_extract_path(base_url: str) -> str:
    return base_url if base_url.endswith("/extract") else f"{base_url}/extract"


def _ictu_search_query(query: str) -> str:
    normalized = normalize_scope_text(query or "")
    if any(marker in normalized for marker in NORMALIZED_ICTU_QUERY_MARKERS):
        return query.strip()
    return f"{query.strip()} {ICTU_WEB_QUERY_MARKER}".strip()


def _ictu_official_search_query(query: str) -> str:
    clean_query = query.strip()
    if f"site:{ICTU_OFFICIAL_DOMAIN}" in clean_query.casefold():
        return clean_query
    return f"site:{ICTU_OFFICIAL_DOMAIN} {clean_query}".strip()


def _is_official_ictu_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").casefold()
    return host == ICTU_OFFICIAL_DOMAIN or host.endswith(f".{ICTU_OFFICIAL_DOMAIN}")


def _is_ictu_web_result(item: dict[str, Any]) -> bool:
    url = str(item.get("url") or item.get("href") or "").strip()
    title = str(item.get("title") or "")
    content = str(item.get("content") or item.get("body") or "")

    host = (urlparse(url).hostname or "").casefold()
    if any(domain in host for domain in ICTU_DOMAINS):
        return True

    haystack = normalize_scope_text(f"{title}\n{url}\n{content}")
    return any(marker in haystack for marker in NORMALIZED_ICTU_QUERY_MARKERS)


def _item_url(item: dict[str, Any]) -> str:
    return str(item.get("url") or item.get("href") or "").strip()


def _extract_text(url: str) -> str:
    extract_base_url = _extract_base_url()
    if not extract_base_url:
        return ""

    try:
        with httpx.Client(timeout=EXTRACT_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = client.post(
                _with_extract_path(extract_base_url),
                json={"url": url, "output_format": "txt"},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        print(f"Web extract unavailable for {url}: {exc}")
        return ""

    if not payload.get("success"):
        return ""
    data = payload.get("data") or {}
    return str(data.get("text") or data.get("raw") or "").strip()


def _search_raw(query: str, *, time_range: str = "") -> list[dict[str, Any]]:
    params = {
        "q": query,
        "format": "json",
    }
    if time_range:
        params["time_range"] = time_range

    try:
        with httpx.Client(timeout=SEARCH_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = client.get(_with_search_path(_search_base_url()), params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        print(f"Web search unavailable, using local data only: {exc}")
        return []

    raw_results = payload.get("results") if isinstance(payload, dict) else []
    return raw_results if isinstance(raw_results, list) else []


def _documents_from_raw_results(
    raw_results: list[dict[str, Any]],
    *,
    limit: int,
    seen_urls: set[str],
    require_official: bool = False,
) -> list[WebSearchDocument]:
    documents: list[WebSearchDocument] = []
    for item in raw_results:
        if not isinstance(item, dict) or not _is_ictu_web_result(item):
            continue

        url = _item_url(item)
        if not url or url in seen_urls or not url.startswith(("http://", "https://")):
            continue
        if require_official and not _is_official_ictu_url(url):
            continue

        seen_urls.add(url)
        title = str(item.get("title") or url).strip()
        snippet = str(item.get("content") or item.get("body") or "").strip()
        extracted = _extract_text(url) if len(documents) < WEB_EXTRACT_RESULT_LIMIT else ""
        text = extracted or snippet
        if not text:
            text = title

        documents.append(
            WebSearchDocument(
                title=title[:220],
                url=url,
                snippet=snippet[:1000],
                text=text[:3000],
            )
        )
        if len(documents) >= limit:
            break
    return documents


def search_web_ictu(query: str, *, limit: int = WEB_SEARCH_RESULT_LIMIT) -> list[WebSearchDocument]:
    if not is_ictu_related_query(query) or not web_search_configured():
        return []

    time_range = "day" if should_use_web_search(query) else ""
    seen_urls: set[str] = set()

    official_docs = _documents_from_raw_results(
        _search_raw(_ictu_official_search_query(query), time_range=time_range),
        limit=limit,
        seen_urls=seen_urls,
        require_official=True,
    )
    if len(official_docs) >= limit:
        return official_docs[:limit]

    broader_docs = _documents_from_raw_results(
        _search_raw(_ictu_search_query(query), time_range=time_range),
        limit=limit - len(official_docs),
        seen_urls=seen_urls,
        require_official=False,
    )

    return [*official_docs, *broader_docs][:limit]
