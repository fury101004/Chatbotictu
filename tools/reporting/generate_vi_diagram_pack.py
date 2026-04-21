from __future__ import annotations

import math
from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont


def _find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "main.py").exists() and (parent / "services").is_dir():
            return parent
    return Path(__file__).resolve().parents[2]


OUT = _find_repo_root() / "reports" / "generated" / "diagram_pack_vi"
OUT.mkdir(parents=True, exist_ok=True)

REG = r"C:\Windows\Fonts\segoeui.ttf"
BOLD = r"C:\Windows\Fonts\segoeuib.ttf"

BW = {
    "bg": "#ffffff",
    "ink": "#111111",
    "line": "#111111",
    "muted": "#444444",
}

PASTEL = {
    "bg": "#ffffff",
    "panel": "#eef4ff",
    "panel_stroke": "#d8e3fb",
    "line": "#7a8fb4",
    "ink": "#263238",
    "agent_fill": "#ffe9c9",
    "agent_stroke": "#e3b56f",
    "blue_fill": "#dff1ff",
    "blue_stroke": "#9fc7ea",
    "green_fill": "#dff7df",
    "green_stroke": "#9fd2a2",
    "orange_fill": "#fff0d8",
    "orange_stroke": "#e5bf7f",
    "pink_fill": "#ffdce8",
    "pink_stroke": "#d8a0b5",
    "purple_fill": "#eee7ff",
    "purple_stroke": "#bdaee8",
}


def rgba(color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(BOLD if bold else REG, size=size)


def wrap_pixels(text: str, fnt: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines = [words[0]]
    for word in words[1:]:
        trial = lines[-1] + " " + word
        if fnt.getlength(trial) <= max_width:
            lines[-1] = trial
        else:
            lines.append(word)
    return lines


def draw_text_block(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    fnt: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    center: bool = True,
    gap: int = 6,
) -> None:
    x1, y1, x2, y2 = box
    lines = wrap_pixels(text, fnt, x2 - x1 - 28)
    total_h = len(lines) * fnt.size + max(0, len(lines) - 1) * gap
    cy = y1 + (y2 - y1 - total_h) // 2
    for line in lines:
        width = int(fnt.getlength(line))
        cx = x1 + (x2 - x1 - width) // 2 if center else x1 + 14
        draw.text((cx, cy), line, font=fnt, fill=fill)
        cy += fnt.size + gap


def draw_label(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    size: int = 22,
    bold: bool = False,
    fill: str = "#111111",
) -> None:
    draw.text((x, y), text, font=font(size, bold), fill=rgba(fill))


def draw_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    fill: tuple[int, int, int, int],
    width: int = 4,
    head: int = 12,
) -> None:
    draw.line([start, end], fill=fill, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    left = (
        end[0] - head * math.cos(angle - math.pi / 6),
        end[1] - head * math.sin(angle - math.pi / 6),
    )
    right = (
        end[0] - head * math.cos(angle + math.pi / 6),
        end[1] - head * math.sin(angle + math.pi / 6),
    )
    draw.polygon([end, left, right], fill=fill)


def draw_dashed_line(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    fill: tuple[int, int, int, int],
    width: int = 4,
    dash: int = 14,
    gap: int = 10,
) -> None:
    total = math.hypot(end[0] - start[0], end[1] - start[1])
    if total == 0:
        return
    dx = (end[0] - start[0]) / total
    dy = (end[1] - start[1]) / total
    distance = 0
    while distance < total:
        seg_end = min(distance + dash, total)
        x1 = start[0] + dx * distance
        y1 = start[1] + dy * distance
        x2 = start[0] + dx * seg_end
        y2 = start[1] + dy * seg_end
        draw.line((x1, y1, x2, y2), fill=fill, width=width)
        distance += dash + gap


def draw_dashed_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    fill: tuple[int, int, int, int],
    width: int = 4,
) -> None:
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    if length < 18:
        draw_arrow(draw, start, end, fill, width)
        return
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    body_end = (int(end[0] - 14 * math.cos(angle)), int(end[1] - 14 * math.sin(angle)))
    draw_dashed_line(draw, start, body_end, fill, width)
    draw_arrow(draw, body_end, end, fill, width)


def draw_poly_arrow(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    fill: tuple[int, int, int, int],
    width: int = 4,
    dashed: bool = False,
) -> None:
    if len(points) < 2:
        return
    for a, b in zip(points[:-2], points[1:-1]):
        if dashed:
            draw_dashed_line(draw, a, b, fill, width)
        else:
            draw.line([a, b], fill=fill, width=width)
    last_start = points[-2]
    last_end = points[-1]
    if dashed:
        draw_dashed_arrow(draw, last_start, last_end, fill, width)
    else:
        draw_arrow(draw, last_start, last_end, fill, width)


def draw_rect_box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    text: str,
    outline: str,
    fill: str = "#ffffff",
    radius: int = 0,
    size: int = 22,
) -> None:
    if radius > 0:
        draw.rounded_rectangle(xy, radius=radius, fill=rgba(fill), outline=rgba(outline), width=3)
    else:
        draw.rectangle(xy, fill=rgba(fill), outline=rgba(outline), width=3)
    draw_text_block(draw, xy, text, font(size, True), rgba("#111111"))


def draw_cylinder(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    text: str,
    outline: str = "#111111",
    fill: str = "#ffffff",
) -> None:
    rx = w // 2
    top_h = 38
    draw.rectangle((x, y + top_h // 2, x + w, y + h - top_h // 2), fill=rgba(fill), outline=rgba(outline), width=3)
    draw.ellipse((x, y, x + w, y + top_h), fill=rgba(fill), outline=rgba(outline), width=3)
    draw.arc((x, y + h - top_h, x + w, y + h), start=0, end=180, fill=rgba(outline), width=3)
    box = (x + 22, y + 50, x + w - 22, y + h - 30)
    draw_text_block(draw, box, text, font(22, True), rgba("#111111"))


def draw_doc_box(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    text: str,
    outline: str,
    fill: str = "#ffffff",
    fold: int = 30,
) -> None:
    points = [
        (x, y),
        (x + w - fold, y),
        (x + w, y + fold),
        (x + w, y + h),
        (x, y + h),
    ]
    draw.polygon(points, fill=rgba(fill), outline=rgba(outline))
    draw.line((x + w - fold, y, x + w - fold, y + fold), fill=rgba(outline), width=3)
    draw.line((x + w - fold, y + fold, x + w, y + fold), fill=rgba(outline), width=3)
    draw.line((x, y, x + w - fold, y), fill=rgba(outline), width=3)
    draw.line((x, y, x, y + h), fill=rgba(outline), width=3)
    draw.line((x, y + h, x + w, y + h), fill=rgba(outline), width=3)
    draw.line((x + w, y + fold, x + w, y + h), fill=rgba(outline), width=3)
    box = (x + 14, y + 10, x + w - 14, y + h - 12)
    draw_text_block(draw, box, text, font(22, True), rgba("#111111"))


def draw_user_icon(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0, outline: str = "#111111") -> None:
    ox = rgba(outline)
    head_r = int(34 * scale)
    body_w = int(88 * scale)
    body_h = int(72 * scale)
    draw.ellipse((x - head_r, y - 2 * head_r, x + head_r, y), outline=ox, width=5)
    draw.arc((x - body_w // 2, y - 10, x + body_w // 2, y + body_h), start=180, end=360, fill=ox, width=5)
    draw.line((x - body_w // 2, y + body_h // 2, x - body_w // 2, y + body_h), fill=ox, width=5)
    draw.line((x + body_w // 2, y + body_h // 2, x + body_w // 2, y + body_h), fill=ox, width=5)


def new_canvas(width: int, height: int, bg: str = "#ffffff") -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (width, height), rgba(bg))
    return img, ImageDraw.Draw(img)


def save_png(image: Image.Image, name: str) -> Path:
    path = OUT / name
    image.convert("RGB").save(path, quality=95)
    return path


def build_rag_basic_bw() -> Path:
    img, draw = new_canvas(1600, 920, BW["bg"])
    line = rgba(BW["line"])

    draw_label(draw, 70, 28, "Sơ đồ RAG cơ bản", 34, True)

    draw_rect_box(draw, (80, 90, 320, 410), "Semantic Tower", BW["ink"])
    draw_rect_box(draw, (470, 170, 770, 340), "Embeddings Model", BW["ink"])
    draw_cylinder(draw, 930, 120, 210, 250, "Vector Store", BW["ink"])
    draw_doc_box(draw, 820, 470, 250, 160, "Context Query Prompt", BW["ink"])
    draw_rect_box(draw, (1280, 110, 1490, 720), "Fine-tuned LLM", BW["ink"])
    draw_doc_box(draw, 520, 730, 250, 110, "Output", BW["ink"])

    draw_user_icon(draw, 125, 600, 1.4, BW["ink"])
    draw_label(draw, 72, 706, "Người dùng", 28, True)

    draw_arrow(draw, (320, 250), (470, 250), line, 4)
    draw_arrow(draw, (770, 250), (930, 250), line, 4)
    draw_dashed_arrow(draw, (1115, 370), (940, 470), line, 3)
    draw_arrow(draw, (1070, 550), (1280, 550), line, 4)
    draw_arrow(draw, (1280, 700), (770, 785), line, 4)
    draw_arrow(draw, (210, 560), (820, 560), line, 4)
    draw_dashed_arrow(draw, (600, 470), (600, 340), line, 3)

    draw_label(draw, 350, 515, "Query", 22, True)
    draw_label(draw, 1025, 395, "Retrieval Results", 22, True)

    return save_png(img, "01_rag_co_ban_den_trang.png")


def build_rag_pipeline_bw() -> Path:
    img, draw = new_canvas(1800, 1000, BW["bg"])
    line = rgba(BW["line"])

    draw_label(draw, 70, 28, "Sơ đồ nạp dữ liệu và truy xuất RAG", 34, True)

    top_boxes = [
        ((90, 120, 320, 240), "Tài liệu gốc"),
        ((380, 120, 620, 240), "Tiền xử lý"),
        ((680, 120, 920, 240), "Chia nhỏ văn bản"),
        ((980, 120, 1260, 240), "Embedding Model"),
    ]
    for box, text in top_boxes:
        draw_rect_box(draw, box, text, BW["ink"])
    draw_cylinder(draw, 1360, 92, 220, 210, "Vector Store", BW["ink"])

    bottom_boxes = [
        ((270, 640, 500, 760), "Câu hỏi"),
        ((590, 640, 870, 760), "Embedding truy vấn"),
        ((970, 620, 1230, 780), "Bộ truy xuất"),
        ((1320, 620, 1590, 780), "Ngữ cảnh + Prompt"),
    ]
    for box, text in bottom_boxes:
        draw_rect_box(draw, box, text, BW["ink"])
    draw_rect_box(draw, (1630, 600, 1760, 800), "LLM", BW["ink"])
    draw_doc_box(draw, 1450, 860, 260, 100, "Câu trả lời", BW["ink"])

    draw_user_icon(draw, 105, 715, 1.2, BW["ink"])
    draw_label(draw, 52, 810, "Người dùng", 28, True)

    draw_arrow(draw, (320, 180), (380, 180), line)
    draw_arrow(draw, (620, 180), (680, 180), line)
    draw_arrow(draw, (920, 180), (980, 180), line)
    draw_arrow(draw, (1260, 180), (1360, 180), line)

    draw_arrow(draw, (160, 695), (270, 695), line)
    draw_arrow(draw, (500, 700), (590, 700), line)
    draw_arrow(draw, (870, 700), (970, 700), line)
    draw_arrow(draw, (1230, 700), (1320, 700), line)
    draw_arrow(draw, (1590, 700), (1630, 700), line)
    draw_arrow(draw, (1695, 800), (1590, 910), line)

    draw_dashed_arrow(draw, (730, 640), (1460, 300), line, 3)
    draw_dashed_arrow(draw, (1470, 302), (1110, 620), line, 3)

    draw_label(draw, 1145, 420, "Top-k đoạn liên quan", 22, True)
    draw_label(draw, 1010, 320, "Câu hỏi được mã hóa", 20, False, BW["muted"])

    return save_png(img, "02_nap_du_lieu_va_truy_xuat_rag_den_trang.png")


def pastel_box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    text: str,
    fill: str,
    outline: str,
    radius: int = 18,
    size: int = 22,
) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=rgba(fill), outline=rgba(outline), width=3)
    draw_text_block(draw, xy, text, font(size, True), rgba(PASTEL["ink"]))


def build_agent_rag_pastel() -> Path:
    img, draw = new_canvas(1800, 1200, PASTEL["bg"])
    line = rgba(PASTEL["line"])

    draw_label(draw, 70, 26, "Agent + RAG + công cụ bên ngoài", 34, True, PASTEL["ink"])

    panel = (360, 90, 1280, 620)
    draw.rounded_rectangle(panel, radius=46, fill=rgba(PASTEL["panel"]), outline=rgba(PASTEL["panel_stroke"]), width=3)
    draw_label(draw, 430, 130, "RAG", 30, True, PASTEL["ink"])

    pastel_box(draw, (455, 300, 600, 368), "Query", PASTEL["green_fill"], PASTEL["green_stroke"], 14, 20)
    pastel_box(draw, (470, 210, 700, 278), "Embedding Model", PASTEL["blue_fill"], PASTEL["blue_stroke"], 14, 20)
    pastel_box(draw, (720, 120, 980, 188), "Query Embedding", PASTEL["orange_fill"], PASTEL["orange_stroke"], 18, 20)
    pastel_box(draw, (1030, 210, 1270, 278), "Vector Database", PASTEL["pink_fill"], PASTEL["pink_stroke"], 18, 20)
    pastel_box(draw, (870, 470, 1120, 555), "Prompt with Context", PASTEL["green_fill"], PASTEL["green_stroke"], 18, 20)
    pastel_box(draw, (470, 470, 620, 538), "LLM", PASTEL["blue_fill"], PASTEL["blue_stroke"], 18, 20)
    for offset in (22, 11, 0):
        draw.rounded_rectangle((1115 - offset, 320 + offset, 1210 - offset, 450 + offset), radius=16, outline=rgba(PASTEL["orange_stroke"]), width=3)
    draw_text_block(draw, (1090, 350, 1225, 420), "Candidates", font(20, True), rgba(PASTEL["ink"]))

    draw_dashed_arrow(draw, (600, 334), (780, 180), line, 3)
    draw_dashed_arrow(draw, (700, 244), (720, 154), line, 3)
    draw_dashed_arrow(draw, (980, 154), (1030, 240), line, 3)
    draw_arrow(draw, (1190, 278), (1160, 320), line, 4)
    draw_dashed_arrow(draw, (1115, 390), (1120, 510), line, 3)
    draw_dashed_arrow(draw, (870, 510), (620, 505), line, 3)
    draw_dashed_arrow(draw, (600, 334), (900, 500), line, 3)

    draw_user_icon(draw, 170, 900, 1.05, PASTEL["ink"])
    draw_label(draw, 105, 995, "User", 28, True, PASTEL["ink"])

    draw.rounded_rectangle((640, 790, 980, 1030), radius=26, fill=rgba(PASTEL["agent_fill"]), outline=rgba(PASTEL["agent_stroke"]), width=3)
    draw_label(draw, 745, 838, "AI Agent", 30, True, PASTEL["ink"])
    pastel_box(draw, (735, 885, 885, 955), "LLM(s)", PASTEL["blue_fill"], PASTEL["blue_stroke"], 18, 20)

    pastel_box(draw, (1230, 720, 1595, 820), "Web Search", PASTEL["orange_fill"], PASTEL["orange_stroke"], 18, 24)
    pastel_box(draw, (1230, 875, 1595, 985), "Some External API", PASTEL["purple_fill"], PASTEL["purple_stroke"], 18, 24)
    pastel_box(draw, (1230, 1040, 1595, 1150), "Knowledge Actions", PASTEL["pink_fill"], PASTEL["pink_stroke"], 18, 24)

    draw_dashed_arrow(draw, (255, 885), (640, 885), line, 3)
    draw_dashed_arrow(draw, (640, 930), (255, 930), line, 3)
    draw_dashed_arrow(draw, (810, 790), (810, 620), line, 3)
    draw_dashed_arrow(draw, (980, 885), (1230, 770), line, 3)
    draw_dashed_arrow(draw, (980, 930), (1230, 930), line, 3)
    draw_dashed_arrow(draw, (980, 975), (1230, 1095), line, 3)

    return save_png(img, "03_agent_rag_pastel.png")


def build_agentic_rag_pastel() -> Path:
    img, draw = new_canvas(1900, 1200, PASTEL["bg"])
    line = rgba(PASTEL["line"])

    draw_label(draw, 70, 26, "Agentic RAG mở rộng", 34, True, PASTEL["ink"])

    panel = (120, 110, 760, 530)
    draw.rounded_rectangle(panel, radius=44, fill=rgba(PASTEL["panel"]), outline=rgba(PASTEL["panel_stroke"]), width=3)
    draw_label(draw, 190, 150, "RAG", 30, True, PASTEL["ink"])
    pastel_box(draw, (180, 220, 370, 295), "User Query", PASTEL["green_fill"], PASTEL["green_stroke"], 18, 20)
    pastel_box(draw, (420, 220, 640, 295), "Retriever", PASTEL["blue_fill"], PASTEL["blue_stroke"], 18, 20)
    pastel_box(draw, (420, 340, 660, 420), "Reranker", PASTEL["orange_fill"], PASTEL["orange_stroke"], 18, 20)
    pastel_box(draw, (190, 350, 360, 425), "Chunks", PASTEL["pink_fill"], PASTEL["pink_stroke"], 18, 20)
    pastel_box(draw, (250, 450, 540, 520), "Prompt with Context", PASTEL["green_fill"], PASTEL["green_stroke"], 18, 20)

    draw_dashed_arrow(draw, (370, 258), (420, 258), line, 3)
    draw_dashed_arrow(draw, (540, 295), (540, 340), line, 3)
    draw_dashed_arrow(draw, (420, 378), (360, 388), line, 3)
    draw_dashed_arrow(draw, (360, 420), (395, 450), line, 3)

    draw_user_icon(draw, 185, 875, 1.05, PASTEL["ink"])
    draw_label(draw, 120, 968, "Người dùng", 28, True, PASTEL["ink"])

    draw.rounded_rectangle((760, 720, 1140, 1020), radius=28, fill=rgba(PASTEL["agent_fill"]), outline=rgba(PASTEL["agent_stroke"]), width=3)
    draw_label(draw, 860, 770, "Agent Orchestrator", 30, True, PASTEL["ink"])
    pastel_box(draw, (840, 830, 1060, 905), "Planner LLM", PASTEL["blue_fill"], PASTEL["blue_stroke"], 18, 20)
    pastel_box(draw, (845, 925, 1055, 995), "Memory", PASTEL["purple_fill"], PASTEL["purple_stroke"], 18, 20)

    pastel_box(draw, (1320, 640, 1720, 740), "Web Search", PASTEL["orange_fill"], PASTEL["orange_stroke"], 18, 24)
    pastel_box(draw, (1320, 800, 1720, 905), "School API / External API", PASTEL["purple_fill"], PASTEL["purple_stroke"], 18, 24)
    pastel_box(draw, (1320, 970, 1720, 1075), "Evaluation / Logging", PASTEL["pink_fill"], PASTEL["pink_stroke"], 18, 24)
    pastel_box(draw, (820, 560, 1080, 640), "Final Answer", PASTEL["green_fill"], PASTEL["green_stroke"], 18, 22)

    draw_dashed_arrow(draw, (270, 870), (760, 870), line, 3)
    draw_dashed_arrow(draw, (760, 915), (270, 915), line, 3)
    draw_dashed_arrow(draw, (950, 720), (520, 530), line, 3)
    draw_dashed_arrow(draw, (1140, 845), (1320, 690), line, 3)
    draw_dashed_arrow(draw, (1140, 885), (1320, 852), line, 3)
    draw_dashed_arrow(draw, (1140, 960), (1320, 1020), line, 3)
    draw_dashed_arrow(draw, (950, 720), (950, 640), line, 3)

    return save_png(img, "04_agentic_rag_mo_rong_pastel.png")


def build_readme(paths: list[Path]) -> Path:
    content = """# Bộ sơ đồ RAG và AI Agent

Bộ này gồm 4 ảnh PNG để đưa vào slide, Word hoặc báo cáo.

## 1. RAG cơ bản
- Tệp ảnh: `01_rag_co_ban_den_trang.png`
- Ý nghĩa: mô tả luồng cơ bản của RAG, trong đó tài liệu được đưa vào mô hình embedding và lưu trong vector store.
- Khi người dùng đặt câu hỏi, hệ thống sinh embedding cho truy vấn, truy xuất các đoạn liên quan, ghép vào prompt rồi đưa cho LLM sinh câu trả lời.
- Sơ đồ này hợp để giải thích tổng quan pipeline RAG theo kiểu đen trắng, nghiêm túc và dễ đưa vào luận văn.

## 2. Nạp dữ liệu và truy xuất RAG
- Tệp ảnh: `02_nap_du_lieu_va_truy_xuat_rag_den_trang.png`
- Ý nghĩa: tách riêng 2 pha lớn là ingestion và retrieval.
- Pha ingestion đi từ tài liệu gốc -> tiền xử lý -> chia nhỏ -> embedding -> vector store.
- Pha retrieval đi từ câu hỏi của người dùng -> embedding truy vấn -> bộ truy xuất -> ngữ cảnh + prompt -> LLM -> câu trả lời.
- Sơ đồ này hợp khi bạn muốn nhấn mạnh quy trình kỹ thuật hơn là chỉ nhìn ở mức tổng quan.

## 3. Agent + RAG + công cụ bên ngoài
- Tệp ảnh: `03_agent_rag_pastel.png`
- Ý nghĩa: AI Agent dùng LLM làm trung tâm và có thể gọi RAG, web search, API ngoài hoặc các hành động tri thức.
- RAG panel bên trên cho thấy cách query được mã hóa, đối chiếu với vector database, lấy candidate, ghép prompt và đưa vào LLM.
- Sơ đồ này hợp để minh họa chatbot thông minh hơn một RAG thông thường, vì nó có thể kết hợp retrieval với tool use.

## 4. Agentic RAG mở rộng
- Tệp ảnh: `04_agentic_rag_mo_rong_pastel.png`
- Ý nghĩa: đây là phiên bản mở rộng của Agent + RAG, bổ sung planner, memory, web search, API và logging/evaluation.
- Planner LLM điều phối xem khi nào cần gọi retrieval, khi nào cần dùng công cụ, và cách tổng hợp kết quả thành final answer.
- Sơ đồ này hợp để đưa vào phần đề xuất kiến trúc hoặc lộ trình nâng cấp hệ thống AI Agent.

## Gợi ý sử dụng
- Nếu cần một ảnh mở đầu cho phần lý thuyết: dùng `01_rag_co_ban_den_trang.png`.
- Nếu cần giải thích pipeline kỹ thuật: dùng `02_nap_du_lieu_va_truy_xuat_rag_den_trang.png`.
- Nếu cần nói về AI Agent: dùng `03_agent_rag_pastel.png` hoặc `04_agentic_rag_mo_rong_pastel.png`.
"""
    readme = OUT / "README.md"
    readme.write_text(content, encoding="utf-8")
    return readme


def main() -> None:
    paths = [
        build_rag_basic_bw(),
        build_rag_pipeline_bw(),
        build_agent_rag_pastel(),
        build_agentic_rag_pastel(),
    ]
    readme = build_readme(paths)
    for path in paths:
        print(path)
    print(readme)


if __name__ == "__main__":
    main()
