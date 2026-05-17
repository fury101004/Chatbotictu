from __future__ import annotations

import logging
from dataclasses import dataclass

from config.settings import settings
from repositories.config_repository import get_runtime_config


logger = logging.getLogger("runtime_config")


@dataclass(frozen=True)
class RuntimeConfig:
    chunk_size: int
    chunk_overlap: int


def _read_int_config(key: str, default: int, *, minimum: int = 0) -> int:
    raw_value = get_runtime_config(key, str(default))
    try:
        value = int(str(raw_value).strip())
    except (TypeError, ValueError):
        logger.warning("Invalid runtime config %s=%r; using %s", key, raw_value, default)
        return default
    if value < minimum:
        logger.warning("Runtime config %s=%r is below minimum %s; using %s", key, value, minimum, default)
        return default
    return value


def load_runtime_config() -> RuntimeConfig:
    return RuntimeConfig(
        chunk_size=_read_int_config("chunk_size", settings.CHUNK_SIZE, minimum=100),
        chunk_overlap=_read_int_config("chunk_overlap", settings.CHUNK_OVERLAP, minimum=0),
    )


def apply_runtime_config() -> RuntimeConfig:
    runtime_config = load_runtime_config()
    settings.CHUNK_SIZE = runtime_config.chunk_size
    settings.CHUNK_OVERLAP = runtime_config.chunk_overlap
    return runtime_config
