from __future__ import annotations

from collections import Counter, deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any

_MAX_RECENT_EVENTS = 500
_EVENT_DETAIL_LIMIT = 320

_LOCK = Lock()
_TOTALS: Counter[str] = Counter()
_RECENT_EVENTS: deque[dict[str, Any]] = deque(maxlen=_MAX_RECENT_EVENTS)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_metadata(metadata: dict[str, Any] | None) -> dict[str, str]:
    if not metadata:
        return {}

    normalized: dict[str, str] = {}
    for key, value in metadata.items():
        normalized[str(key)] = str(value)
    return normalized


def record_429(source: str, *, detail: str = "", metadata: dict[str, Any] | None = None) -> None:
    normalized_source = (source or "unknown").strip().lower()
    event = {
        "timestamp": _utc_now_iso(),
        "source": normalized_source,
        "detail": (detail or "")[:_EVENT_DETAIL_LIMIT],
        "metadata": _normalize_metadata(metadata),
    }

    with _LOCK:
        _TOTALS["all"] += 1
        _TOTALS[normalized_source] += 1
        _RECENT_EVENTS.append(event)


def snapshot_429_stats(limit_recent: int = 40) -> dict[str, Any]:
    normalized_limit = max(0, int(limit_recent))

    with _LOCK:
        totals = dict(_TOTALS)
        recent_events = list(_RECENT_EVENTS)

    if normalized_limit:
        recent_events = recent_events[-normalized_limit:]
    else:
        recent_events = []

    return {
        "totals": totals,
        "recent_events": recent_events,
        "recent_event_count": len(recent_events),
        "distinct_sources": len([key for key in totals if key != "all"]),
    }


def reset_429_stats() -> None:
    with _LOCK:
        _TOTALS.clear()
        _RECENT_EVENTS.clear()


__all__ = ["record_429", "reset_429_stats", "snapshot_429_stats"]
