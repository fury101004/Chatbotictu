from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass(slots=True)
class UploadBatchResult:
    status: str = "done"
    added: int = 0
    updated: int = 0
    failed: int = 0
    msg: str = ""
    real_speed: Optional[str] = None
    detail: dict[str, list[str]] = field(
        default_factory=lambda: {"added": [], "updated": [], "failed": []}
    )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class HistoryEntry:
    role: str
    content: str
    time: str


@dataclass(slots=True)
class VectorManagerPayload:
    chunks_by_file: dict[str, list[dict]]
    total_chunks: int
    total_files: int

    def to_dict(self) -> dict:
        return {
            "chunks_by_file": self.chunks_by_file,
            "total_chunks": self.total_chunks,
            "total_files": self.total_files,
        }



