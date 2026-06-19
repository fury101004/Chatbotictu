from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from config.settings import settings
from services.rag.ictu_scope_service import is_ictu_related_query, normalize_scope_text


logger = logging.getLogger("web_search")

WEB_SEARCH_RESULT_LIMIT = 4
WEB_EXTRACT_RESULT_LIMIT = 2
SEARCH_TIMEOUT_SECONDS = 30.0
EXTRACT_TIMEOUT_SECONDS = 35.0
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0

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


# ---------------------------------------------------------------------------
# Startup diagnostics — Task 2
# ---------------------------------------------------------------------------

def _log_startup_config() -> None:
    """Log web-search configuration at import time so Azure container logs
    show immediately whether the required URLs are present."""
    searxng_ok = bool(_clean_base_url(settings.SEARXNG_URL))
    trafilatura_ok = bool(_clean_base_url(settings.TRAFILATURA_URL))
    logger.info(
        "[web_search] startup: SEARXNG configured=%s  TRAFILATURA configured=%s",
        searxng_ok,
        trafilatura_ok,
    )
    if not searxng_ok:
        logger.warning(
            "[web_search] SEARXNG_URL is empty — web search will be DISABLED. "
            "Set SEARXNG_URL (or SEARXNG_API / SEAXNG_API) in Azure App Settings."
        )
    if not trafilatura_ok:
        logger.warning(
            "[web_search] TRAFILATURA_URL is empty — text extraction will be DISABLED. "
            "Set TRAFILATURA_URL (or TRAFILATURA_API) in Azure App Settings."
        )


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _clean_base_url(value: str) -> str:
    return value.strip().rstrip("/")


def _search_base_url() -> str:
    return _clean_base_url(settings.SEARXNG_URL)


def _extract_base_url() -> str:
    return _clean_base_url(settings.TRAFILATURA_URL)


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


def _web_search_time_range(query: str) -> str:
    normalized = normalize_scope_text(query or "")
    return "day" if normalize_scope_text("hôm nay") in normalized else ""


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


# ---------------------------------------------------------------------------
# Retry helper — Task 4
# ---------------------------------------------------------------------------

def _is_retryable(exc: Exception) -> bool:
    """Return True for transient network errors worth retrying."""
    if isinstance(exc, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
        return True
    if isinstance(exc, httpx.ConnectError):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {502, 503, 504, 429}:
        return True
    return False


# ---------------------------------------------------------------------------
# HTTP calls with logging + retry — Tasks 3 & 4
# ---------------------------------------------------------------------------

def _extract_text(url: str) -> str:
    extract_base_url = _extract_base_url()
    if not extract_base_url:
        logger.debug("[web_search] _extract_text skipped: TRAFILATURA_URL not configured")
        return ""

    target = _with_extract_path(extract_base_url)
    for attempt in range(1, _MAX_RETRIES + 1):
        t0 = time.monotonic()
        try:
            with httpx.Client(timeout=EXTRACT_TIMEOUT_SECONDS, follow_redirects=True) as client:
                response = client.post(target, json={"url": url, "output_format": "txt"})
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                response.raise_for_status()
                payload = response.json()

            logger.info(
                "[web_search] extract url=%s status=%s elapsed=%dms attempt=%d/%d",
                url, response.status_code, elapsed_ms, attempt, _MAX_RETRIES,
            )

            if not payload.get("success"):
                logger.warning("[web_search] extract returned success=false for %s", url)
                return ""

            data = payload.get("data") or {}
            text = str(data.get("text") or data.get("raw") or "").strip()
            logger.info("[web_search] extract result: %d chars from %s", len(text), url)
            return text

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            if _is_retryable(exc) and attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "[web_search] extract attempt=%d/%d FAILED url=%s elapsed=%dms "
                    "error=%s — retrying in %.1fs",
                    attempt, _MAX_RETRIES, url, elapsed_ms, exc, delay,
                )
                time.sleep(delay)
                continue

            logger.exception(
                "[web_search] extract FAILED url=%s elapsed=%dms attempt=%d/%d",
                url, elapsed_ms, attempt, _MAX_RETRIES,
            )
            return ""

    return ""


def _search_raw(query: str, *, time_range: str = "") -> list[dict[str, Any]]:
    search_base = _search_base_url()
    if not search_base:
        logger.warning("[web_search] _search_raw skipped: SEARXNG_URL not configured")
        return []

    target = _with_search_path(search_base)
    params: dict[str, str] = {"q": query, "format": "json"}
    if time_range:
        params["time_range"] = time_range

    for attempt in range(1, _MAX_RETRIES + 1):
        t0 = time.monotonic()
        try:
            with httpx.Client(timeout=SEARCH_TIMEOUT_SECONDS, follow_redirects=True) as client:
                response = client.get(target, params=params)
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                response.raise_for_status()
                payload = response.json()

            raw_results = payload.get("results") if isinstance(payload, dict) else []
            results = raw_results if isinstance(raw_results, list) else []

            logger.info(
                "[web_search] search query=%r url=%s status=%s elapsed=%dms "
                "raw_results=%d attempt=%d/%d",
                query, target, response.status_code, elapsed_ms,
                len(results), attempt, _MAX_RETRIES,
            )
            return results

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            if _is_retryable(exc) and attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "[web_search] search attempt=%d/%d FAILED query=%r url=%s "
                    "elapsed=%dms error=%s — retrying in %.1fs",
                    attempt, _MAX_RETRIES, query, target, elapsed_ms, exc, delay,
                )
                time.sleep(delay)
                continue

            logger.exception(
                "[web_search] search FAILED query=%r url=%s elapsed=%dms attempt=%d/%d",
                query, target, elapsed_ms, attempt, _MAX_RETRIES,
            )
            return []

    return []


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

    logger.info(
        "[web_search] _documents_from_raw_results: raw=%d filtered=%d require_official=%s",
        len(raw_results), len(documents), require_official,
    )
    return documents


def search_web_ictu(query: str, *, limit: int = WEB_SEARCH_RESULT_LIMIT) -> list[WebSearchDocument]:
    if not is_ictu_related_query(query):
        logger.debug("[web_search] search_web_ictu skipped: query not ICTU-related")
        return []

    if not web_search_configured():
        logger.warning(
            "[web_search] search_web_ictu DISABLED: SEARXNG_URL is empty. "
            "Set SEARXNG_URL in environment / Azure App Settings."
        )
        return []

    t0 = time.monotonic()
    time_range = _web_search_time_range(query)
    seen_urls: set[str] = set()

    official_docs = _documents_from_raw_results(
        _search_raw(_ictu_official_search_query(query), time_range=time_range),
        limit=limit,
        seen_urls=seen_urls,
        require_official=True,
    )
    if len(official_docs) >= limit:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "[web_search] search_web_ictu done: %d articles, elapsed=%dms (official only)",
            len(official_docs), elapsed_ms,
        )
        return official_docs[:limit]

    broader_docs = _documents_from_raw_results(
        _search_raw(_ictu_search_query(query), time_range=time_range),
        limit=limit - len(official_docs),
        seen_urls=seen_urls,
        require_official=False,
    )

    combined = [*official_docs, *broader_docs][:limit]
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "[web_search] search_web_ictu done: %d articles (official=%d broader=%d) elapsed=%dms",
        len(combined), len(official_docs), len(broader_docs), elapsed_ms,
    )
    return combined


# ---------------------------------------------------------------------------
# Diagnostic helper — used by /debug/news endpoint (Task 5)
# ---------------------------------------------------------------------------

def diagnose_web_search() -> dict[str, Any]:
    """Run a full diagnostic check of the web search pipeline.

    Returns a structured dict suitable for JSON serialization.
    """
    import socket

    errors: list[str] = []
    result: dict[str, Any] = {
        "searxng_configured": False,
        "trafilatura_configured": False,
        "searxng_url": "",
        "trafilatura_url": "",
        "dns_ok": False,
        "http_ok": False,
        "articles_found": 0,
        "latest_titles": [],
        "errors": errors,
        "timing_ms": 0,
    }

    t0 = time.monotonic()
    searxng_url = _search_base_url()
    trafilatura_url = _extract_base_url()

    result["searxng_configured"] = bool(searxng_url)
    result["trafilatura_configured"] = bool(trafilatura_url)
    result["searxng_url"] = searxng_url or "(not set)"
    result["trafilatura_url"] = trafilatura_url or "(not set)"

    if not searxng_url:
        errors.append("SEARXNG_URL is not configured. Web search is DISABLED.")
        result["timing_ms"] = int((time.monotonic() - t0) * 1000)
        return result

    # DNS check
    parsed = urlparse(searxng_url)
    hostname = parsed.hostname or ""
    try:
        addr_info = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
        result["dns_ok"] = bool(addr_info)
    except socket.gaierror as exc:
        errors.append(f"DNS resolution failed for {hostname}: {exc}")
        result["timing_ms"] = int((time.monotonic() - t0) * 1000)
        return result

    # HTTP connectivity check
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(searxng_url)
            result["http_ok"] = resp.status_code < 500
            if resp.status_code >= 500:
                errors.append(f"SearXNG returned HTTP {resp.status_code}")
    except Exception as exc:
        errors.append(f"HTTP connectivity check failed: {exc}")
        result["timing_ms"] = int((time.monotonic() - t0) * 1000)
        return result

    # Sample search
    try:
        docs = search_web_ictu("ictu tin tức mới nhất", limit=5)
        result["articles_found"] = len(docs)
        result["latest_titles"] = [doc.title for doc in docs]
        if not docs:
            errors.append("search_web_ictu returned 0 articles for test query.")
    except Exception as exc:
        errors.append(f"search_web_ictu raised: {exc}")

    result["timing_ms"] = int((time.monotonic() - t0) * 1000)
    return result


# ---------------------------------------------------------------------------
# Run startup diagnostics on module import
# ---------------------------------------------------------------------------
_log_startup_config()
