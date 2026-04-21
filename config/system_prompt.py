from __future__ import annotations

from pathlib import Path

SYSTEM_PROMPT_PATH = Path("data/systemprompt.md")

EMERGENCY_SYSTEM_PROMPT = (
    "Bạn là trợ lý AI của ICTU. Chỉ trả lời dựa trên ngữ cảnh hiện tại."
)


def read_system_prompt() -> str:
    if not SYSTEM_PROMPT_PATH.exists():
        return ""
    try:
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def ensure_system_prompt_file() -> str:
    prompt = read_system_prompt()
    if prompt:
        return prompt

    SYSTEM_PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SYSTEM_PROMPT_PATH.write_text(EMERGENCY_SYSTEM_PROMPT, encoding="utf-8")
    return EMERGENCY_SYSTEM_PROMPT


def get_system_prompt() -> str:
    return ensure_system_prompt_file()


def save_system_prompt(content: str) -> str:
    cleaned = content.strip() or ensure_system_prompt_file()
    SYSTEM_PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SYSTEM_PROMPT_PATH.write_text(cleaned, encoding="utf-8")
    return cleaned
