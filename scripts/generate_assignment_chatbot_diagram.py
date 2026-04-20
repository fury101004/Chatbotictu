from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "reports" / "generated" / "assignment_chatbot_diagrams"

REG = r"C:\Windows\Fonts\segoeui.ttf"
BOLD = r"C:\Windows\Fonts\segoeuib.ttf"

W = 2200
H = 1450

PALETTE = {
    "bg": "#f6f9ff",
    "card": "#ffffff",
    "rag_fill": "#eef4ff",
    "rag_border": "#cad8fb",
    "title_bg": "#102542",
    "title_fg": "#ffffff",
    "text": "#1f2a44",
    "muted": "#52607a",
    "line": "#7a8eb8",
    "blue_fill": "#dff3ff",
    "blue_border": "#8cccf0",
    "green_fill": "#ddf7df",
    "green_border": "#8fcf99",
    "amber_fill": "#fff1cc",
    "amber_border": "#f0c56a",
    "pink_fill": "#ffe0eb",
    "pink_border": "#e8a6c4",
    "purple_fill": "#efe6ff",
    "purple_border": "#bca1ee",
    "orange_fill": "#ffe6cf",
    "orange_border": "#f0af67",
    "gray_fill": "#edf2f7",
    "gray_border": "#a8b3c7",
    "navy_fill": "#dce8ff",
    "navy_border": "#7fa2e6",
}


def rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    value = hex_color.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4)) + (alpha,)


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


def rounded_card(
    base: Image.Image,
    box: tuple[int, int, int, int],
    *,
    fill: str,
    outline: str,
    radius: int = 28,
    shadow_alpha: int = 20,
) -> None:
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    x1, y1, x2, y2 = box
    shadow_draw.rounded_rectangle(
        (x1 + 10, y1 + 12, x2 + 10, y2 + 12),
        radius=radius,
        fill=(15, 23, 42, shadow_alpha),
    )
    base.alpha_composite(shadow)
    ImageDraw.Draw(base).rounded_rectangle(
        box,
        radius=radius,
        fill=rgba(fill),
        outline=rgba(outline),
        width=3,
    )


def draw_text_block(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    *,
    fnt: ImageFont.FreeTypeFont,
    fill: str,
    max_width: int,
    gap: int = 8,
) -> int:
    lines = wrap_pixels(text, fnt, max_width)
    cy = y
    for line in lines:
        draw.text((x, cy), line, font=fnt, fill=rgba(fill))
        cy += fnt.size + gap
    return cy


def draw_centered_lines(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    lines: list[str],
    *,
    fnt: ImageFont.FreeTypeFont,
    fill: str,
    gap: int = 6,
) -> None:
    x1, y1, x2, y2 = box
    total_h = len(lines) * fnt.size + max(0, len(lines) - 1) * gap
    cy = y1 + (y2 - y1 - total_h) // 2
    for line in lines:
        width = int(fnt.getlength(line))
        cx = x1 + (x2 - x1 - width) // 2
        draw.text((cx, cy), line, font=fnt, fill=rgba(fill))
        cy += fnt.size + gap


def draw_box(
    base: Image.Image,
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    title: str,
    subtitle: str | None = None,
    fill: str,
    outline: str,
    radius: int = 22,
) -> None:
    rounded_card(base, box, fill=fill, outline=outline, radius=radius, shadow_alpha=14)
    x1, y1, x2, y2 = box
    title_font = font(24, True)
    body_font = font(19)
    title_lines = wrap_pixels(title, title_font, x2 - x1 - 34)
    draw_centered_lines(draw, (x1 + 16, y1 + 16, x2 - 16, y1 + 70), title_lines, fnt=title_font, fill=PALETTE["text"])
    if subtitle:
        body_lines = wrap_pixels(subtitle, body_font, x2 - x1 - 34)
        draw_centered_lines(draw, (x1 + 16, y1 + 70, x2 - 16, y2 - 18), body_lines, fnt=body_font, fill=PALETTE["muted"], gap=4)


def draw_chip(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    text: str,
    fill: str,
    outline: str,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=(y2 - y1) // 2, fill=rgba(fill), outline=rgba(outline), width=2)
    draw_centered_lines(draw, box, [text], fnt=font(18, True), fill=PALETTE["text"])


def draw_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    color: str,
    width: int = 6,
    dashed: bool = False,
    dash: int = 18,
    gap: int = 12,
) -> None:
    sx, sy = start
    ex, ey = end
    if dashed:
        length = math.hypot(ex - sx, ey - sy)
        if length == 0:
            return
        dx = (ex - sx) / length
        dy = (ey - sy) / length
        distance = 0.0
        while distance < length - dash:
            seg_start = (sx + dx * distance, sy + dy * distance)
            seg_end = (sx + dx * min(distance + dash, length - dash), sy + dy * min(distance + dash, length - dash))
            draw.line([seg_start, seg_end], fill=rgba(color), width=width)
            distance += dash + gap
    else:
        draw.line([start, end], fill=rgba(color), width=width)

    angle = math.atan2(ey - sy, ex - sx)
    arrow_len = 22
    wing = 10
    p1 = (
        ex - arrow_len * math.cos(angle) + wing * math.sin(angle),
        ey - arrow_len * math.sin(angle) - wing * math.cos(angle),
    )
    p2 = (
        ex - arrow_len * math.cos(angle) - wing * math.sin(angle),
        ey - arrow_len * math.sin(angle) + wing * math.cos(angle),
    )
    draw.polygon([end, p1, p2], fill=rgba(color))


def draw_avatar(base: Image.Image, draw: ImageDraw.ImageDraw, center: tuple[int, int]) -> None:
    cx, cy = center
    draw.ellipse((cx - 34, cy - 68, cx + 34, cy), fill=rgba("#203a6f"))
    draw.ellipse((cx - 22, cy - 48, cx + 22, cy - 4), fill=rgba("#ffffff"))
    draw.pieslice((cx - 44, cy - 84, cx + 44, cy + 4), start=200, end=-20, fill=rgba("#203a6f"))
    draw.rounded_rectangle((cx - 54, cy + 12, cx + 54, cy + 88), radius=34, fill=rgba("#203a6f"))
    draw.rectangle((cx - 15, cy + 12, cx + 15, cy + 76), fill=rgba("#ffffff"))


def _draw_candidate_stack(base: Image.Image, draw: ImageDraw.ImageDraw, origin: tuple[int, int]) -> None:
    x, y = origin
    boxes = [
        (x + 24, y + 24, x + 194, y + 154),
        (x + 12, y + 12, x + 182, y + 142),
        (x, y, x + 170, y + 130),
    ]
    for idx, box in enumerate(boxes):
        rounded_card(
            base,
            box,
            fill=PALETTE["card"] if idx == 2 else PALETTE["orange_fill"],
            outline=PALETTE["orange_border"],
            radius=18,
            shadow_alpha=10,
        )
    draw_centered_lines(
        draw,
        boxes[-1],
        ["Candidate", "chunks"],
        fnt=font(22, True),
        fill=PALETTE["text"],
    )


def _draw_rag_legend(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    label_font = font(20, True)
    text_font = font(18)
    draw.text((x, y), "Nguồn tri thức đã index:", font=label_font, fill=rgba(PALETTE["text"]))
    draw.text(
        (x, y + 34),
        "Sổ tay sinh viên | Quy định | FAQ | Upload | Web KB Cache",
        font=text_font,
        fill=rgba(PALETTE["muted"]),
    )


def build_general_diagram() -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (W, H), rgba(PALETTE["bg"]))
    draw = ImageDraw.Draw(image)

    title_font = font(44, True)
    subtitle_font = font(22)
    section_font = font(28, True)
    small_font = font(18)

    draw.ellipse((1680, -40, 2260, 520), fill=rgba("#d9e7ff", 190))
    draw.ellipse((-100, 980, 420, 1520), fill=rgba("#ddf7df", 180))

    rounded_card(image, (70, 48, 2130, 180), fill=PALETTE["title_bg"], outline="#1d4577", radius=34, shadow_alpha=28)
    draw.text((116, 84), "Bản thiết kế chatbot tổng quát ICTU", font=title_font, fill=rgba(PALETTE["title_fg"]))
    draw.text(
        (116, 138),
        "Vẽ lại theo bố cục ảnh tham chiếu: khối RAG ở tầng trên, AI Agent ở trung tâm, công cụ hỗ trợ ở bên phải.",
        font=subtitle_font,
        fill=rgba("#dce8ff"),
    )

    rag_panel = (380, 225, 1840, 760)
    rounded_card(image, rag_panel, fill=PALETTE["rag_fill"], outline=PALETTE["rag_border"], radius=40, shadow_alpha=18)
    draw.text((430, 264), "RAG / Retrieval-Augmented Generation", font=section_font, fill=rgba(PALETTE["text"]))
    draw.text(
        (430, 308),
        "Tầng trên chịu trách nhiệm truy xuất ngữ cảnh từ vector database và ghép prompt có căn cứ trước khi gọi LLM.",
        font=small_font,
        fill=rgba(PALETTE["muted"]),
    )

    query_box = (510, 500, 740, 590)
    embedding_model_box = (500, 350, 770, 438)
    query_embedding_box = (930, 292, 1208, 380)
    vector_db_box = (1360, 350, 1650, 438)
    prompt_box = (940, 596, 1270, 708)
    llm_box = (610, 612, 820, 696)

    draw_box(image, draw, query_box, title="Query", subtitle="Câu hỏi + ngữ cảnh phiên", fill=PALETTE["green_fill"], outline=PALETTE["green_border"])
    draw_box(image, draw, embedding_model_box, title="Embedding Model", subtitle="Mã hóa câu hỏi để tìm tài liệu gần nghĩa", fill=PALETTE["blue_fill"], outline=PALETTE["blue_border"])
    draw_box(image, draw, query_embedding_box, title="Query Embedding", subtitle="Vector đại diện cho truy vấn hiện tại", fill=PALETTE["amber_fill"], outline=PALETTE["amber_border"])
    draw_box(image, draw, vector_db_box, title="Vector Database", subtitle="ChromaDB + metadata + hybrid retrieval", fill=PALETTE["pink_fill"], outline=PALETTE["pink_border"])
    draw_box(image, draw, prompt_box, title="Prompt with Context", subtitle="Ghép candidate chunks, luật bot và câu hỏi hiện tại", fill=PALETTE["green_fill"], outline=PALETTE["green_border"])
    draw_box(image, draw, llm_box, title="LLM", subtitle="Sinh câu trả lời grounded", fill=PALETTE["blue_fill"], outline=PALETTE["blue_border"])
    _draw_candidate_stack(image, draw, (1560, 500))
    _draw_rag_legend(draw, 940, 710)

    agent_box = (860, 890, 1380, 1155)
    rounded_card(image, agent_box, fill="#ffe7c8", outline=PALETTE["orange_border"], radius=34, shadow_alpha=20)
    draw.text((930, 940), "AI Agent / Chat Orchestrator", font=font(34, True), fill=rgba(PALETTE["text"]))
    draw.text(
        (932, 990),
        "Điều phối guardrail, router, tool calling, gọi RAG, gọi web search và trả đáp án về Web/API.",
        font=font(20),
        fill=rgba(PALETTE["muted"]),
    )
    draw_chip(draw, (944, 1040, 1098, 1084), text="Guardrail", fill=PALETTE["green_fill"], outline=PALETTE["green_border"])
    draw_chip(draw, (1112, 1040, 1238, 1084), text="Router", fill=PALETTE["amber_fill"], outline=PALETTE["amber_border"])
    draw_chip(draw, (1254, 1040, 1442, 1084), text="Tool Calling", fill=PALETTE["purple_fill"], outline=PALETTE["purple_border"])
    draw_chip(draw, (1085, 1096, 1222, 1140), text="LLM(s)", fill=PALETTE["blue_fill"], outline=PALETTE["blue_border"])

    user_box = (86, 960, 320, 1160)
    rounded_card(image, user_box, fill=PALETTE["card"], outline=PALETTE["gray_border"], radius=28, shadow_alpha=16)
    draw_avatar(image, draw, (202, 1016))
    draw_centered_lines(draw, (110, 1088, 298, 1140), ["Người dùng"], fnt=font(28, True), fill=PALETTE["text"])
    draw_centered_lines(draw, (110, 1130, 298, 1160), ["Web UI / REST API"], fnt=font(19), fill=PALETTE["muted"])

    web_box = (1650, 840, 2090, 940)
    api_box = (1650, 982, 2090, 1082)
    kb_box = (1650, 1124, 2090, 1224)
    memory_box = (920, 1210, 1320, 1310)

    draw_box(image, draw, web_box, title="Web Search ICTU", subtitle="Tìm thông báo mới trên domain chính thức", fill=PALETTE["amber_fill"], outline=PALETTE["amber_border"])
    draw_box(image, draw, api_box, title="External API / Partner API", subtitle="Tích hợp hệ thống ngoài khi có quyền gọi", fill=PALETTE["purple_fill"], outline=PALETTE["purple_border"])
    draw_box(image, draw, kb_box, title="Knowledge Base / Upload", subtitle="Upload tài liệu, duyệt Q&A, re-index vector store", fill=PALETTE["pink_fill"], outline=PALETTE["pink_border"])
    draw_box(image, draw, memory_box, title="Session Memory + Logs", subtitle="Lưu lịch sử chat, nguồn và retrieved ids", fill=PALETTE["gray_fill"], outline=PALETTE["gray_border"])

    draw_arrow(draw, (320, 1020), (860, 1020), color=PALETTE["line"], width=5, dashed=True)
    draw_arrow(draw, (860, 1080), (320, 1080), color=PALETTE["line"], width=5, dashed=True)
    draw_arrow(draw, (1120, 890), (1120, 760), color=PALETTE["line"], width=6, dashed=True)
    draw_arrow(draw, (1380, 1014), (1650, 888), color=PALETTE["line"], width=5, dashed=True)
    draw_arrow(draw, (1380, 1022), (1650, 1032), color=PALETTE["line"], width=5, dashed=True)
    draw_arrow(draw, (1380, 1078), (1650, 1170), color=PALETTE["line"], width=5, dashed=True)
    draw_arrow(draw, (1120, 1155), (1120, 1210), color=PALETTE["line"], width=5, dashed=True)

    draw_arrow(draw, (625, 500), (625, 438), color=PALETTE["line"], width=5, dashed=True)
    draw_arrow(draw, (770, 394), (930, 336), color=PALETTE["line"], width=5, dashed=True)
    draw_arrow(draw, (740, 530), (930, 340), color=PALETTE["line"], width=5, dashed=True)
    draw_arrow(draw, (1208, 336), (1360, 394), color=PALETTE["line"], width=5, dashed=True)
    draw_arrow(draw, (1500, 438), (1620, 500), color=PALETTE["line"], width=5, dashed=True)
    draw_arrow(draw, (740, 570), (940, 642), color=PALETTE["line"], width=5, dashed=True)
    draw_arrow(draw, (1560, 620), (1270, 652), color=PALETTE["line"], width=5, dashed=True)
    draw_arrow(draw, (940, 648), (820, 650), color=PALETTE["line"], width=5, dashed=True)
    draw_arrow(draw, (710, 696), (1020, 890), color=PALETTE["line"], width=5, dashed=True)
    draw_arrow(draw, (1650, 1170), (1600, 438), color=PALETTE["line"], width=4, dashed=True)

    draw.text(
        (102, 1348),
        "Sơ đồ này chi tiết hóa nhiệm vụ 'Bản thiết kế chatbot tổng quát': AI Agent điều phối, RAG truy xuất ngữ cảnh, còn web search / API / KB là các nhánh hỗ trợ.",
        font=small_font,
        fill=rgba(PALETTE["muted"]),
    )

    output = OUT_DIR / "chatbot_tong_quat_chi_tiet.png"
    image.convert("RGB").save(output, quality=95)
    return output


def generate_diagram_assets() -> dict[str, Path]:
    png_path = build_general_diagram()
    return {"general_design_png": png_path}


if __name__ == "__main__":
    assets = generate_diagram_assets()
    for value in assets.values():
        print(value)
