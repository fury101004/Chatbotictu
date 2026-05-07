from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Query

from services.ictu_scope_service import is_ictu_related_query, normalize_scope_text


logger = logging.getLogger("searxng")

_ICTU_NEWS_KEYWORDS = (
    "tin tức",
    "tin mới",
    "thông báo",
    "thông báo mới",
    "sự kiện",
    "hội thảo",
)
_ICTU_DYNAMIC_KEYWORDS = (
    "hôm nay",
    "hiện tại",
    "mới nhất",
    "gần đây",
    "cập nhật",
    "năm nay",
    "tin tức",
    "tin mới",
    "tuyển sinh",
    "xét tuyển",
    "điểm chuẩn",
    "điểm sàn",
    "điểm trúng tuyển",
    "chỉ tiêu",
    "học phí",
    "lệ phí",
    "thông báo mới",
    "thông báo tuyển sinh",
    "lịch tuyển sinh",
    "lịch nhập học",
    "lịch thi",
    "lịch học",
    "lịch nghỉ",
    "hạn nộp",
    "deadline",
    "nộp hồ sơ",
    "nhập học",
    "đề án tuyển sinh",
    "phương thức xét tuyển",
    "nguyện vọng",
    "học bổng",
    "sự kiện",
    "hội thảo",
    "tuyển dụng",
    "việc làm",
)
_NORMALIZED_ICTU_NEWS_KEYWORDS = tuple(normalize_scope_text(keyword) for keyword in _ICTU_NEWS_KEYWORDS)
_NORMALIZED_ICTU_DYNAMIC_KEYWORDS = tuple(normalize_scope_text(keyword) for keyword in _ICTU_DYNAMIC_KEYWORDS)


def _normalize_query(query: str) -> str:
    return normalize_scope_text(query or "")


def _is_news_query(query: str) -> bool:
    q = _normalize_query(query)
    if not q:
        return False
    return is_ictu_related_query(q) and any(keyword in q for keyword in _NORMALIZED_ICTU_NEWS_KEYWORDS)


def _is_realtime_query(query: str) -> bool:
    q = _normalize_query(query)
    if not q:
        return False
    return is_ictu_related_query(q) and any(keyword in q for keyword in _NORMALIZED_ICTU_DYNAMIC_KEYWORDS)


def _item_to_result(item: dict, url_key: str = "href") -> dict | None:
    url = (item.get(url_key) or item.get("url") or item.get("href") or "").strip()
    if not url or not url.startswith(("http://", "https://")):
        return None
    return {
        "url": url,
        "href": url,
        "title": (item.get("title") or "").strip(),
        "content": (item.get("body") or item.get("content") or "").strip(),
    }


def _search_ddgs(query: str, max_results: int = 12, time_range: str = "") -> list[dict[str, Any]]:
    try:
        from ddgs import DDGS
    except Exception as exc:
        logger.warning("DDGS is not installed or unavailable: %s", exc)
        return []

    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    q = query.strip()
    timelimit = "d" if time_range == "day" else None

    if _is_news_query(q):
        try:
            for raw in DDGS().news(q, max_results=max_results, region="vn-vi", timelimit="d"):
                item = _item_to_result(raw, url_key="url")
                if item and item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    results.append(item)
                if len(results) >= max_results:
                    break
        except Exception as exc:
            logger.debug("DDGS news() failed, falling back to text(): %s", exc)

    if len(results) < max_results:
        try:
            kwargs: dict[str, Any] = {"max_results": max_results, "region": "vn-vi"}
            if timelimit or _is_realtime_query(q):
                kwargs["timelimit"] = timelimit or "d"
            for raw in DDGS().text(q, **kwargs):
                item = _item_to_result(raw)
                if item and item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    results.append(item)
                if len(results) >= max_results:
                    break
        except Exception as exc:
            logger.warning("DDGS text search failed: %s", exc)

    return results[:max_results]


app = FastAPI(
    title="SearXNG Search Service",
    version="1.0.0",
    description="Web search API compatible with the SearXNG /search JSON format.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/search")
def search(
    q: str = Query(..., description="Query tìm kiếm"),
    format: str = Query("json", description="json"),
    time_range: str = Query("", description="day|week"),
) -> dict[str, Any]:
    del format
    if not q or len(q.strip()) < 2:
        return {"results": []}

    query = q.strip()
    logger.info("Search: %s (time_range=%s)", query[:80], time_range or "none")
    return {"results": _search_ddgs(query, max_results=12, time_range=time_range)}
