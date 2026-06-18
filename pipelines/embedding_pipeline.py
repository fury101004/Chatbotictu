from __future__ import annotations

import os
import socket
import traceback
from pathlib import Path
from typing import Any, Callable, Optional

_CACHE_ENV_VARS = (
    "HF_HOME",
    "HUGGINGFACE_HUB_CACHE",
    "TRANSFORMERS_CACHE",
    "SENTENCE_TRANSFORMERS_HOME",
    "TORCH_HOME",
    "XDG_CACHE_HOME",
)


def _cache_path_status(path_value: str) -> str:
    if not path_value:
        return "unset"
    try:
        path = Path(path_value)
        path.mkdir(parents=True, exist_ok=True)
        if os.access(path, os.W_OK):
            return "writable"
        return "NOT WRITABLE"
    except OSError as exc:
        return f"error: {exc}"


def _log_embedding_cache_state(stage: str) -> None:
    print(f"[EMBEDDING] Cache state ({stage}):")
    for env_name in _CACHE_ENV_VARS:
        value = os.getenv(env_name, "").strip()
        print(f"[EMBEDDING]   {env_name}={value or '(unset)'} [{_cache_path_status(value)}]")


def _raise_embedding_load_error(exc: BaseException, *, model_name: str, stage: str) -> None:
    _log_embedding_cache_state(stage)
    message = (
        f"Failed to load embedding model '{model_name}' ({stage}): {exc}. "
        "On Azure App Service, /home/site is read-only. "
        "Set HF_HOME, HUGGINGFACE_HUB_CACHE, TRANSFORMERS_CACHE, "
        "SENTENCE_TRANSFORMERS_HOME, TORCH_HOME, and XDG_CACHE_HOME to /home/data/... "
        "or rely on startup.sh + config.settings bootstrap. "
        "If a previous download was interrupted, remove *.lock files under the HF cache hub directory."
    )
    print(f"[EMBEDDING] ERROR: {message}")
    print(f"[EMBEDDING] Traceback:\n{traceback.format_exc()}")
    raise RuntimeError(message) from exc


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
    _log_embedding_cache_state("before_load")

    local_model_path = resolve_local_model_path()
    use_local_model = local_model_path is not None
    if use_local_model:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        print(f"[EMBEDDING] Using local model cache: {local_model_path}")
    else:
        print(f"[EMBEDDING] Local model cache not found; will download if network is available")

    selected_model_name = str(local_model_path) if use_local_model else model_name
    print(f"[EMBEDDING] Loading embedding model: {selected_model_name}")
    try:
        return embedding_factory(
            model_name=selected_model_name,
            local_files_only=use_local_model,
        )
    except OSError as exc:
        print(f"[EMBEDDING] OSError on first load attempt: {exc}")
        print("[EMBEDDING] Retrying with /tmp/huggingface cache fallback...")
        os.environ["HF_HOME"] = "/tmp/huggingface/hf-cache"
        os.environ["HUGGINGFACE_HUB_CACHE"] = "/tmp/huggingface/hf-cache/hub"
        os.environ["TRANSFORMERS_CACHE"] = "/tmp/huggingface/transformers"
        os.environ["SENTENCE_TRANSFORMERS_HOME"] = "/tmp/huggingface/sentence-transformers"
        os.environ["TORCH_HOME"] = "/tmp/huggingface/.cache/torch"
        os.environ["XDG_CACHE_HOME"] = "/tmp/huggingface/.cache"
        for d in (
            "/tmp/huggingface/hf-cache/hub",
            "/tmp/huggingface/transformers",
            "/tmp/huggingface/sentence-transformers",
            "/tmp/huggingface/.cache/torch",
            "/tmp/huggingface/.cache",
        ):
            Path(d).mkdir(parents=True, exist_ok=True)
        _log_embedding_cache_state("retry_tmp")
        try:
            return embedding_factory(
                model_name=model_name,
                local_files_only=False,
            )
        except OSError as retry_exc:
            _raise_embedding_load_error(retry_exc, model_name=model_name, stage="retry_tmp")


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
