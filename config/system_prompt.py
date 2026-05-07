from __future__ import annotations

from pathlib import Path

from config.settings import settings
from shared.prompt_loader import load_prompt_text


SYSTEM_PROMPT_PATH = Path(settings.SYSTEM_PROMPT_PATH)
MINIMAL_SYSTEM_PROMPT = (
    "Ban la tro ly AI cua ICTU.\n"
    "Chi tra loi dua tren ngu canh cua luot hien tai.\n"
    'Neu khong co thong tin lien quan, tra loi: "Thong tin nay hien chua co trong tai lieu cua em."'
)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _get_default_system_prompt() -> str:
    return load_prompt_text("system_prompt.md") or MINIMAL_SYSTEM_PROMPT


def read_system_prompt() -> str:
    return _read_text(SYSTEM_PROMPT_PATH)


def ensure_system_prompt_file() -> str:
    prompt = read_system_prompt()
    if prompt:
        return prompt

    prompt = _get_default_system_prompt()
    SYSTEM_PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SYSTEM_PROMPT_PATH.write_text(prompt, encoding="utf-8")
    return prompt


def get_system_prompt() -> str:
    return ensure_system_prompt_file()


def save_system_prompt(content: str) -> str:
    cleaned = content.strip() or ensure_system_prompt_file()
    SYSTEM_PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SYSTEM_PROMPT_PATH.write_text(cleaned, encoding="utf-8")
    return cleaned
