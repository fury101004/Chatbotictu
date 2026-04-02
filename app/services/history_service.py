"""Business logic around chat history."""

from __future__ import annotations

import io
from typing import Dict, List

from app.models.history import clear_history, get_history_by_user, save_chat


class PdfExportUnavailableError(RuntimeError):
    """Raised when the optional PDF export dependency is unavailable."""


def list_history_for_api(user_id: str) -> List[Dict[str, str]]:
    return get_history_by_user(user_id, descending=True)


def list_history_for_rag(user_id: str) -> List[Dict[str, str]]:
    return get_history_by_user(user_id, descending=False)


def clear_user_history(user_id: str) -> None:
    clear_history(user_id)


def save_exchange(user_id: str, question: str, answer: str) -> None:
    save_chat(user_id, question, answer)


def format_history_as_text(history: List[Dict[str, str]]) -> str:
    lines: List[str] = []
    for item in history:
        lines.append(f"[{item['timestamp']}]")
        lines.append(f"User: {item['question']}")
        lines.append(f"Bot: {item['answer']}")
        lines.append("")
    return "\n".join(lines).strip() + ("\n" if history else "")


def export_history_as_txt(user_id: str) -> io.BytesIO:
    history = list_history_for_rag(user_id)
    return io.BytesIO(format_history_as_text(history).encode("utf-8"))


def export_history_as_pdf(user_id: str) -> io.BytesIO:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import simpleSplit
        from reportlab.pdfgen import canvas
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise PdfExportUnavailableError(
            "Tinh nang export PDF can cai them reportlab."
        ) from exc

    history = list_history_for_rag(user_id)
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)

    page_width, page_height = A4
    margin_x = 40
    start_y = page_height - 50
    line_height = 16
    max_width = page_width - (margin_x * 2)

    text = pdf.beginText(margin_x, start_y)
    text.setFont("Helvetica", 10)
    text.setLeading(line_height)

    def write_line(line: str) -> None:
        nonlocal text
        if text.getY() <= 50:
            pdf.drawText(text)
            pdf.showPage()
            text = pdf.beginText(margin_x, start_y)
            text.setFont("Helvetica", 10)
            text.setLeading(line_height)
        text.textLine(line)

    for item in history:
        block_lines = [
            f"[{item['timestamp']}]",
            f"User: {item['question']}",
            f"Bot: {item['answer']}",
            "",
        ]
        for block_line in block_lines:
            wrapped_lines = simpleSplit(block_line, "Helvetica", 10, max_width) or [""]
            for wrapped_line in wrapped_lines:
                write_line(wrapped_line)

    pdf.drawText(text)
    pdf.save()
    buffer.seek(0)
    return buffer
