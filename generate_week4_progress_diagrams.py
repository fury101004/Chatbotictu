from __future__ import annotations

from pathlib import Path
from typing import List, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont


ROOT_DIR = Path(__file__).resolve().parent
ASSET_DIR = ROOT_DIR / "report_assets"

WHITE = "#FFFFFF"
SLATE = "#0F172A"
BLUE = "#2563EB"
LIGHT_BLUE = "#DBEAFE"
GREEN = "#059669"
LIGHT_GREEN = "#D1FAE5"
AMBER = "#D97706"
LIGHT_AMBER = "#FEF3C7"
ROSE = "#E11D48"
LIGHT_ROSE = "#FFE4E6"
GRAY = "#475569"
LIGHT_GRAY = "#F8FAFC"
ARROW = "#334155"


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibrib.ttf" if bold else r"C:\Windows\Fonts\calibri.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
    )
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    words = text.split()
    if not words:
        return [""]

    lines: List[str] = []
    current = words[0]
    for word in words[1:]:
        tentative = f"{current} {word}"
        width = draw.textbbox((0, 0), tentative, font=font)[2]
        if width <= max_width:
            current = tentative
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _draw_centered_multiline(
    draw: ImageDraw.ImageDraw,
    box: Tuple[int, int, int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
    *,
    line_gap: int = 8,
) -> None:
    left, top, right, bottom = box
    lines: List[str] = []
    for paragraph in text.splitlines() or [""]:
        wrapped = _wrap_text(draw, paragraph, font, max_width=right - left - 30)
        lines.extend(wrapped if wrapped else [""])
    metrics = [draw.textbbox((0, 0), line, font=font) for line in lines]
    heights = [metric[3] - metric[1] for metric in metrics]
    total_height = sum(heights) + (line_gap * max(0, len(lines) - 1))
    y = top + ((bottom - top - total_height) / 2)

    for line, metric, height in zip(lines, metrics, heights):
        width = metric[2] - metric[0]
        x = left + ((right - left - width) / 2)
        draw.text((x, y), line, font=font, fill=fill)
        y += height + line_gap


def _draw_box(
    draw: ImageDraw.ImageDraw,
    box: Tuple[int, int, int, int],
    text: str,
    *,
    fill: str,
    outline: str,
    text_color: str = SLATE,
    radius: int = 24,
    font: ImageFont.ImageFont | None = None,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=4)
    _draw_centered_multiline(draw, box, text, font or _font(28), text_color)


def _draw_arrow(
    draw: ImageDraw.ImageDraw,
    start: Tuple[int, int],
    end: Tuple[int, int],
    *,
    color: str = ARROW,
    width: int = 8,
    head: int = 18,
) -> None:
    x1, y1 = start
    x2, y2 = end
    draw.line((x1, y1, x2, y2), fill=color, width=width)

    if x1 == x2:
        direction = 1 if y2 > y1 else -1
        draw.polygon(
            [
                (x2, y2),
                (x2 - head, y2 - (direction * head)),
                (x2 + head, y2 - (direction * head)),
            ],
            fill=color,
        )
        return

    direction = 1 if x2 > x1 else -1
    draw.polygon(
        [
            (x2, y2),
            (x2 - (direction * head), y2 - head),
            (x2 - (direction * head), y2 + head),
        ],
        fill=color,
    )


def _draw_title(draw: ImageDraw.ImageDraw, text: str, width: int) -> None:
    font = _font(42, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (width - (bbox[2] - bbox[0])) / 2
    draw.text((x, 38), text, font=font, fill=SLATE)


def _create_canvas(width: int = 1800, height: int = 1200) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((24, 24, width - 24, height - 24), radius=28, outline="#CBD5E1", width=3)
    return image, draw


def build_workflow_diagram(output_path: Path) -> None:
    image, draw = _create_canvas()
    body_font = _font(28, bold=True)
    note_font = _font(24)
    width, _ = image.size

    _draw_title(draw, "Sơ đồ luồng xử lý câu hỏi của AI Agent - Tuần 3", width)

    main_boxes: Sequence[Tuple[Tuple[int, int, int, int], str, str, str]] = [
        ((520, 150, 1280, 245), "Người dùng đặt câu hỏi", LIGHT_BLUE, BLUE),
        ((520, 305, 1280, 400), "Agent phân tích ý định và chọn route phù hợp", LIGHT_GREEN, GREEN),
        ((520, 460, 1280, 555), "Retriever truy xuất tài liệu liên quan từ vector store", LIGHT_AMBER, AMBER),
        ((520, 615, 1280, 710), "Reranker sắp xếp tài liệu và tạo context", LIGHT_ROSE, ROSE),
        ((520, 770, 1280, 865), "LLM sinh câu trả lời dựa trên context", LIGHT_BLUE, BLUE),
        ((520, 925, 1280, 1020), "Trả kết quả về giao diện và lưu lịch sử hội thoại", LIGHT_GREEN, GREEN),
    ]

    for box, text, fill, outline in main_boxes:
        _draw_box(draw, box, text, fill=fill, outline=outline, font=body_font)

    for index in range(len(main_boxes) - 1):
        current = main_boxes[index][0]
        next_box = main_boxes[index + 1][0]
        _draw_arrow(
            draw,
            ((current[0] + current[2]) // 2, current[3]),
            ((next_box[0] + next_box[2]) // 2, next_box[1]),
        )

    memory_box = (120, 300, 400, 405)
    kb_box = (1370, 435, 1680, 595)
    _draw_box(
        draw,
        memory_box,
        "Bộ nhớ hội thoại\nLịch sử hội thoại gần nhất",
        fill=LIGHT_GRAY,
        outline=GRAY,
        font=note_font,
    )
    _draw_box(
        draw,
        kb_box,
        "Kho tri thức\nhandbook | policy | faq\nCơ sở dữ liệu véc-tơ FAISS",
        fill=LIGHT_GRAY,
        outline=GRAY,
        font=note_font,
    )

    _draw_arrow(draw, (400, 352), (520, 352))
    _draw_arrow(draw, (1370, 515), (1280, 515))

    footer = "Luồng hiện tại tương ứng với các bước memory -> route -> retrieve -> answer trong rag_service.py"
    footer_bbox = (160, 1080, 1640, 1145)
    _draw_box(
        draw,
        footer_bbox,
        footer,
        fill="#EFF6FF",
        outline="#93C5FD",
        font=_font(22),
        text_color=GRAY,
        radius=18,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


def build_architecture_diagram(output_path: Path) -> None:
    image, draw = _create_canvas()
    width, _ = image.size

    _draw_title(draw, "Sơ đồ kiến trúc hệ thống AI Agent - Tuần 4", width)

    user_box = (720, 120, 1080, 210)
    ui_box = (520, 275, 1280, 390)
    controller_box = (520, 455, 1280, 570)
    service_box = (400, 645, 980, 980)
    knowledge_box = (1040, 645, 1600, 810)
    storage_box = (1040, 855, 1600, 980)
    llm_box = (1320, 345, 1680, 455)

    _draw_box(draw, user_box, "Người dùng / Sinh viên", fill=LIGHT_BLUE, outline=BLUE, font=_font(30, bold=True))
    _draw_box(
        draw,
        ui_box,
        "Lớp giao diện\nWeb chat interface\nHTML - CSS - JavaScript - templates/static",
        fill=LIGHT_GREEN,
        outline=GREEN,
        font=_font(28),
    )
    _draw_box(
        draw,
        controller_box,
        "Lớp điều phối\nFlask app - app/routes/ui.py - app/routes/api.py",
        fill=LIGHT_AMBER,
        outline=AMBER,
        font=_font(28),
    )
    _draw_box(
        draw,
        service_box,
        "Lớp nghiệp vụ\nchat_service\nrag_service\nhistory_service\nllm_service\nreranker",
        fill=LIGHT_ROSE,
        outline=ROSE,
        font=_font(28),
    )
    _draw_box(
        draw,
        knowledge_box,
        "Lớp tri thức\napp/data\nclean_md - rag_md - data\n498 policy | 8 handbook | 10 faq\nvector_db FAISS",
        fill=LIGHT_BLUE,
        outline=BLUE,
        font=_font(26),
    )
    _draw_box(
        draw,
        storage_box,
        "Lớp lưu trữ\napp/models/history.py\nSQLite chat.db",
        fill=LIGHT_GREEN,
        outline=GREEN,
        font=_font(26),
    )
    _draw_box(
        draw,
        llm_box,
        "Ollama / LLM",
        fill=LIGHT_GRAY,
        outline=GRAY,
        font=_font(28, bold=True),
    )

    _draw_arrow(draw, (900, 210), (900, 275))
    _draw_arrow(draw, (900, 390), (900, 455))
    _draw_arrow(draw, (900, 570), (900, 645))
    _draw_arrow(draw, (980, 740), (1040, 740))
    _draw_arrow(draw, (980, 915), (1040, 915))
    _draw_arrow(draw, (1280, 455), (1320, 455))
    _draw_arrow(draw, (1320, 400), (1280, 730))

    note_box = (120, 1035, 1680, 1120)
    _draw_box(
        draw,
        note_box,
        "Kiến trúc hiện tại của dự án đã có đầy đủ giao diện, route, service, dữ liệu, vector store, LLM và lưu lịch sử hội thoại.",
        fill="#FFF7ED",
        outline="#FDBA74",
        font=_font(22),
        text_color=GRAY,
        radius=18,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


def main() -> int:
    build_workflow_diagram(ASSET_DIR / "workflow_tuan_3.png")
    build_architecture_diagram(ASSET_DIR / "kien_truc_tuan_4.png")
    print(f"Đã tạo sơ đồ trong thư mục: {ASSET_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
