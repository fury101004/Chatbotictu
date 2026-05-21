from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from config.settings import settings


TEST_QUESTION_DATASET = settings.PROJECT_ROOT / "docs" / "evaluation" / "ictu_30_questions_dataset.json"


@lru_cache(maxsize=1)
def get_evaluation_test_questions() -> list[dict[str, Any]]:
    if not TEST_QUESTION_DATASET.exists():
        return []

    try:
        raw_items = json.loads(TEST_QUESTION_DATASET.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    result: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        result.append(
            {
                "index": index,
                "id": str(item.get("id") or f"test_{index:03d}"),
                "group": str(item.get("group") or "local_data"),
                "question": question,
                "expected_tool": str(item.get("expected_tool") or ""),
                "expected_flow": str(item.get("expected_flow") or ""),
                "expected_source_contains": [
                    str(source)
                    for source in item.get("expected_source_contains", [])
                    if str(source).strip()
                ],
            }
        )
    return result
