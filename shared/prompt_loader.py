from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any


PROMPT_ROOT = Path(__file__).resolve().parents[1] / "config" / "prompts"


def _resolve_prompt_path(name: str | Path) -> Path:
    candidate = (PROMPT_ROOT / Path(name)).resolve()
    candidate.relative_to(PROMPT_ROOT.resolve())
    return candidate


@lru_cache(maxsize=64)
def load_prompt_text(name: str) -> str:
    return _resolve_prompt_path(name).read_text(encoding="utf-8").strip()


def render_prompt(name: str, **variables: Any) -> str:
    prompt = load_prompt_text(name)
    rendered = prompt.format(**{key: value for key, value in variables.items()})
    return rendered.strip()


def clear_prompt_cache() -> None:
    load_prompt_text.cache_clear()
