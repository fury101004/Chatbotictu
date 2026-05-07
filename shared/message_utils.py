from __future__ import annotations

from typing import Any


def message_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(message_content(item) for item in value)
    if isinstance(value, dict):
        if "text" in value:
            return str(value["text"])
        if "content" in value:
            return message_content(value["content"])
    return str(value)
