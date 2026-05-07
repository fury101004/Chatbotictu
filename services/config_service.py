from __future__ import annotations

from config.settings import settings
from config.db import set_config
from config.system_prompt import get_system_prompt, save_system_prompt
from services.llm_service import (
    PRIMARY_MODEL_NAME,
    get_configured_model_labels,
    model_rotation_mode,
)



def get_config_page_payload() -> dict:
    raw_prompt = get_system_prompt()
    clean_lines = []
    for line in raw_prompt.splitlines():
        stripped = line.rstrip()
        clean_lines.append(stripped)

    beautiful_prompt = "\n".join(clean_lines).strip() + "\n"
    return {
        "chunk_size": settings.CHUNK_SIZE,
        "chunk_overlap": settings.CHUNK_OVERLAP,
        "bot_rules": beautiful_prompt,
        "model_name": PRIMARY_MODEL_NAME,
        "model_names": get_configured_model_labels(),
        "model_rotation": model_rotation_mode(),
    }



def update_runtime_config(
    *,
    chunk_size: int,
    chunk_overlap: int,
    bot_rules: str,
    reingest: bool,
    reingest_callback,
) -> dict:
    old_chunk = settings.CHUNK_SIZE
    old_overlap = settings.CHUNK_OVERLAP

    settings.CHUNK_SIZE = chunk_size
    settings.CHUNK_OVERLAP = chunk_overlap
    set_config("chunk_size", str(chunk_size))
    set_config("chunk_overlap", str(chunk_overlap))
    cleaned_prompt = save_system_prompt(bot_rules)
    set_config("bot_rules", cleaned_prompt)

    need_reingest = (old_chunk != chunk_size or old_overlap != chunk_overlap) or reingest
    msg = "Lưu cấu hình thành công!"

    if need_reingest:
        total_files, total_chunks = reingest_callback()
        if total_files:
            msg = f"RE-INGEST HOÀN TẤT! {total_files} file -> {total_chunks} chunks"

    return {"msg": msg, "reingested": need_reingest}

