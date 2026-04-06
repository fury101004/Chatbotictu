from config.settings import settings


def split_text(text: str, chunk_size=None, chunk_overlap=None):
    words = text.split()
    size = chunk_size or settings.CHUNK_SIZE
    overlap = chunk_overlap or settings.CHUNK_OVERLAP
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i : i + size])
        chunks.append(chunk)
        i += size - overlap
    return chunks or [""]


def assign_level(word_count: int) -> int:
    if word_count < 100:
        return 1
    if word_count < 300:
        return 2
    if word_count < 600:
        return 3
    if word_count < 1000:
        return 4
    return 5
