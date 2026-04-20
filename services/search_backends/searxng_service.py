from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Query


logger = logging.getLogger("searxng")

_NEWS_KEYWORDS = ["báo", "tin tức", "news", "chiến sự", "xung đột", "iran", "israel", "ukraine"]
_REALTIME_KEYWORDS = ["giá vàng", "tỷ giá", "tỉ giá", "usd", "vnd", "thời tiết", "weather", "gold", "sjc", "exchange"]


def _is_news_query(query: str) -> bool:
    q = query.lower().strip()
    return any(keyword in q for keyword in _NEWS_KEYWORDS)


def _is_realtime_query(query: str) -> bool:
    q = query.lower().strip()
    return any(keyword in q for keyword in _REALTIME_KEYWORDS)


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
