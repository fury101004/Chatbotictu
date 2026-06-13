from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def isolate_runtime_state_between_tests(tmp_path, monkeypatch):
    from config.limiter import limiter
    from services.memory_store import MemoryStore

    test_memory_store = MemoryStore(db_path=tmp_path / "chat_memory.db")
    monkeypatch.setattr(
        "services.chat.chat_service.get_default_memory_store",
        lambda: test_memory_store,
    )

    storage = getattr(limiter, "_storage", None)
    if storage is not None and hasattr(storage, "reset"):
        storage.reset()
    yield
