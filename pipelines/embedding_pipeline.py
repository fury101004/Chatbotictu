from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Any, Callable, Optional


def _ensure_cache_dirs_writable() -> None:
    """Đảm bảo các thư mục cache HuggingFace/SentenceTransformers tồn tại
    và có quyền ghi. Quan trọng trên Azure App Service nơi /home/site
    là read-only.

    Nếu biến env chưa được đặt hoặc trỏ tới đường dẫn không ghi được,
    fallback sang /tmp/huggingface.
    """
    fallback_root = Path("/tmp/huggingface")

    cache_vars = {
        "HF_HOME": "hf-cache",
        "HUGGINGFACE_HUB_CACHE": os.path.join("hf-cache", "hub"),
        "TRANSFORMERS_CACHE": "transformers",
        "SENTENCE_TRANSFORMERS_HOME": "sentence-transformers",
        "TORCH_HOME": os.path.join(".cache", "torch"),
    }

    for env_name, sub_dir in cache_vars.items():
        current = os.getenv(env_name, "").strip()
        if current:
            p = Path(current)
            try:
                p.mkdir(parents=True, exist_ok=True)
                if os.access(p, os.W_OK):
                    continue  # Đường dẫn hiện tại OK
            except OSError:
                pass

        # Fallback: dùng /tmp/huggingface/...
        fallback_path = fallback_root / sub_dir
        try:
            fallback_path.mkdir(parents=True, exist_ok=True)
            os.environ[env_name] = str(fallback_path)
            print(f"[EMBEDDING CACHE] {env_name} -> {fallback_path} (fallback)")
        except OSError as exc:
            print(f"[EMBEDDING CACHE] CẢNH BÁO: Không thể tạo {fallback_path}: {exc}")


def build_embedding_function(
    *,
    current_embedding_function: Any,
    resolve_local_model_path: Callable[[], Optional[Path]],
    embedding_factory: Callable[..., Any],
    model_name: str,
) -> Any:
    if current_embedding_function is not None:
        return current_embedding_function

    # Đảm bảo thư mục cache có quyền ghi trước khi tải model
    _ensure_cache_dirs_writable()

    local_model_path = resolve_local_model_path()
    use_local_model = local_model_path is not None
    if use_local_model:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

    selected_model_name = str(local_model_path) if use_local_model else model_name
    print(f"Loading embedding model: {selected_model_name}")
    try:
        return embedding_factory(
            model_name=selected_model_name,
            local_files_only=use_local_model,
        )
    except PermissionError as exc:
        print(f"[EMBEDDING] PermissionError khi tải model: {exc}")
        print(f"[EMBEDDING] Thử fallback cache sang /tmp/huggingface...")
        # Force tất cả cache về /tmp và thử lại
        os.environ["HF_HOME"] = "/tmp/huggingface/hf-cache"
        os.environ["HUGGINGFACE_HUB_CACHE"] = "/tmp/huggingface/hf-cache/hub"
        os.environ["TRANSFORMERS_CACHE"] = "/tmp/huggingface/transformers"
        os.environ["SENTENCE_TRANSFORMERS_HOME"] = "/tmp/huggingface/sentence-transformers"
        os.environ["TORCH_HOME"] = "/tmp/huggingface/.cache/torch"
        for d in ("/tmp/huggingface/hf-cache/hub", "/tmp/huggingface/transformers",
                   "/tmp/huggingface/sentence-transformers", "/tmp/huggingface/.cache/torch"):
            Path(d).mkdir(parents=True, exist_ok=True)
        return embedding_factory(
            model_name=model_name,
            local_files_only=False,
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
