from __future__ import annotations

from config.db import (
    add_uploaded_file as _add_uploaded_file,
    clear_uploaded_files as _clear_uploaded_files,
    delete_uploaded_file as _delete_uploaded_file,
    get_uploaded_files as _get_uploaded_files,
)


def list_uploaded_files() -> list[dict[str, str]]:
    return _get_uploaded_files()


def record_uploaded_file(*, filename: str, tool_name: str, storage_path: str) -> None:
    _add_uploaded_file(filename=filename, tool_name=tool_name, storage_path=storage_path)


def remove_uploaded_file(storage_path: str) -> None:
    _delete_uploaded_file(storage_path)


def clear_uploaded_file_records() -> None:
    _clear_uploaded_files()
