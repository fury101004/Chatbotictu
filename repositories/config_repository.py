from __future__ import annotations

from config.db import get_config as _get_config, set_config as _set_config


def get_runtime_config(key: str, default: str = "") -> str:
    return _get_config(key, default)


def set_runtime_config(key: str, value: str) -> None:
    _set_config(key, value)
