from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_TEXT_SUFFIXES = {".md", ".markdown", ".txt"}
_ALLOWED_MIME_TYPES = {
    ".md": {"text/markdown", "text/x-markdown", "text/plain"},
    ".markdown": {"text/markdown", "text/x-markdown", "text/plain"},
    ".txt": {"text/plain"},
}
_BINARY_SIGNATURES = (
    b"%PDF-",
    b"PK\x03\x04",
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
)
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class UploadValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ValidatedTextUpload:
    filename: str
    content: bytes
    text: str
    content_type: str


def _validate_filename(raw_filename: str) -> str:
    filename = str(raw_filename or "").strip()
    if not filename:
        raise UploadValidationError("missing filename")
    if len(filename) > 180:
        raise UploadValidationError("filename is too long")
    if filename != Path(filename).name or "/" in filename or "\\" in filename or ".." in filename:
        raise UploadValidationError("dangerous filename")
    if filename.startswith(".") or ":" in filename or any(ord(char) < 32 for char in filename):
        raise UploadValidationError("dangerous filename")
    if Path(filename).stem.upper() in _WINDOWS_RESERVED_NAMES:
        raise UploadValidationError("dangerous filename")
    return filename


def _validate_mime_type(suffix: str, content_type: str) -> str:
    normalized = str(content_type or "").split(";", 1)[0].strip().casefold()
    if not normalized or normalized == "application/octet-stream":
        return normalized
    if normalized not in _ALLOWED_MIME_TYPES[suffix]:
        raise UploadValidationError(f"extension and MIME type do not match ({suffix} / {normalized})")
    return normalized


def _decode_text(content: bytes) -> str:
    if any(content.startswith(signature) for signature in _BINARY_SIGNATURES) or b"\x00" in content:
        raise UploadValidationError("content signature is not a supported text document")
    try:
        text = content.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise UploadValidationError("content is not valid UTF-8 text") from exc
    if not text.strip():
        raise UploadValidationError("file is empty")
    sample = text[:4096]
    printable = sum(char.isprintable() or char in "\r\n\t" for char in sample)
    if sample and printable / len(sample) < 0.9:
        raise UploadValidationError("content signature is not a supported text document")
    return text


def validate_text_upload(
    *,
    filename: str,
    content: bytes,
    content_type: str = "",
    max_size_bytes: int,
) -> ValidatedTextUpload:
    safe_filename = _validate_filename(filename)
    suffix = Path(safe_filename).suffix.casefold()
    if suffix not in SUPPORTED_TEXT_SUFFIXES:
        raise UploadValidationError("unsupported file type; only .md/.markdown/.txt are allowed")
    if not content:
        raise UploadValidationError("file is empty")
    if len(content) > max_size_bytes:
        raise UploadValidationError(f"file too large; maximum is {max_size_bytes // (1024 * 1024)}MB")
    normalized_mime = _validate_mime_type(suffix, content_type)
    text = _decode_text(content)
    return ValidatedTextUpload(
        filename=safe_filename,
        content=content,
        text=text,
        content_type=normalized_mime,
    )

