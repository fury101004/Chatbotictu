from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Any, Callable, Optional


def build_embedding_function(
    *,
    current_embedding_function: Any,
    resolve_local_model_path: Callable[[], Optional[Path]],
    embedding_factory: Callable[..., Any],
    model_name: str,
) -> Any:
    if current_embedding_function is not None:
        return current_embedding_function

    local_model_path = resolve_local_model_path()
    use_local_model = local_model_path is not None
    if use_local_model:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

    selected_model_name = str(local_model_path) if use_local_model else model_name
    print(f"Loading embedding model: {selected_model_name}")
    return embedding_factory(
        model_name=selected_model_name,
        local_files_only=use_local_model,
    )


def embedding_backend_ready(
    *,
    resolve_local_model_path: Callable[[], Optional[Path]],
    network_host: str = "huggingface.co",
    network_port: int = 443,
    timeout: float = 0.75,
) -> bool:
    local_model_path = resolve_local_model_path()
    if local_model_path is not None:
        print(f"Embedding backend ready via local cache: {local_model_path}")
        return True

    try:
        with socket.create_connection((network_host, network_port), timeout=timeout):
            return True
    except OSError as exc:
        print(f"Embedding backend unavailable, skip vector indexing: {exc}")
        return False
