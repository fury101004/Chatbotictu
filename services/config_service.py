from __future__ import annotations

from pathlib import Path

from config.settings import settings
from config.db import save_system_prompt, set_config



def get_config_page_payload() -> dict:
    prompt_path = Path("data/systemprompt.md")
    if prompt_path.exists():
        raw_prompt = prompt_path.read_text(encoding="utf-8")
    else:
        raw_prompt = "# Chua co file systemprompt.md - vui long tao tai thu muc data/"

    clean_lines = []
    for line in raw_prompt.splitlines():
        stripped = line.rstrip()
        clean_lines.append(stripped)

    beautiful_prompt = "\n".join(clean_lines).strip() + "\n"
    return {
        "chunk_size": settings.CHUNK_SIZE,
        "chunk_overlap": settings.CHUNK_OVERLAP,
        "bot_rules": beautiful_prompt,
        "model_name": "gemini-2.5-flash",
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
    save_system_prompt(bot_rules)

    need_reingest = (old_chunk != chunk_size or old_overlap != chunk_overlap) or reingest
    msg = "Luu cau hinh thanh cong!"

    if need_reingest:
        total_files, total_chunks = reingest_callback()
        if total_files:
            msg = f"RE-INGEST HOAN TAT! {total_files} file -> {total_chunks} chunks"

    return {"msg": msg, "reingested": need_reingest}

