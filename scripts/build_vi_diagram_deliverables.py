from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from textwrap import wrap
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(r"E:\new-test")
PACK_DIR = ROOT / "reports" / "generated" / "diagram_pack_vi"
SLIDES_DIR = PACK_DIR / "slides"
SLIDES_DIR.mkdir(parents=True, exist_ok=True)

REG = r"C:\Windows\Fonts\segoeui.ttf"
BOLD = r"C:\Windows\Fonts\segoeuib.ttf"

A4_W = 2480
A4_H = 3508
SLIDE_W = 1920
SLIDE_H = 1080
PPT_CX = 12192000
PPT_CY = 6858000
EMU_PER_INCH = 914400

PALETTE = {
    "bg": "#f8fbff",
    "card": "#ffffff",
    "soft": "#e9f1fb",
    "border": "#cfdef0",
    "ink": "#233042",
    "muted": "#526173",
    "accent": "#325ea8",
    "green": "#e7f6e8",
    "orange": "#fff1db",
    "pink": "#fde6ee",
    "purple": "#efeaff",
}

DIAGRAMS = [
    {
        "title": "RAG cơ bản",
        "filename": "01_rag_co_ban_den_trang.png",
        "summary": "Luồng chuẩn của RAG: tài liệu được embedding, lưu vào vector store, sau đó truy xuất ngữ cảnh để hỗ trợ LLM trả lời chính xác hơn.",
        "bullets": [
            "Nhấn mạnh pipeline tổng quan từ truy vấn đến câu trả lời.",
            "Hợp cho phần lý thuyết hoặc giới thiệu nền tảng RAG.",
        ],
        "tag": "Tổng quan",
        "tag_fill": PALETTE["green"],
    },
    {
        "title": "Nạp dữ liệu và truy xuất RAG",
        "filename": "02_nap_du_lieu_va_truy_xuat_rag_den_trang.png",
        "summary": "Tách rõ hai pha ingestion và retrieval để người đọc thấy dữ liệu đi vào hệ thống thế nào, rồi được lấy ra phục vụ trả lời ra sao.",
        "bullets": [
            "Pha 1: làm sạch, chia nhỏ, embedding, lưu vector.",
            "Pha 2: mã hóa truy vấn, truy xuất top-k, ghép prompt và gọi LLM.",
        ],
        "tag": "Kỹ thuật",
        "tag_fill": PALETTE["orange"],
    },
    {
        "title": "Agent + RAG + công cụ bên ngoài",
        "filename": "03_agent_rag_pastel.png",
        "summary": "AI Agent điều phối nhiều khả năng: dùng RAG để truy xuất tri thức, web search để lấy thông tin mới và API ngoài để thực hiện tác vụ.",
        "bullets": [
            "Phù hợp để giải thích kiến trúc chatbot thông minh hơn RAG thuần.",
            "Cho thấy vai trò của LLM như bộ điều phối trung tâm.",
        ],
        "tag": "Agent",
        "tag_fill": PALETTE["pink"],
    },
    {
        "title": "Agentic RAG mở rộng",
        "filename": "04_agentic_rag_mo_rong_pastel.png",
        "summary": "Bản mở rộng có planner, memory và logging để điều phối quyết định, lưu trạng thái và theo dõi hiệu năng toàn hệ thống.",
        "bullets": [
            "Hợp cho phần đề xuất nâng cấp hoặc kiến trúc tương lai.",
            "Làm rõ cách Agent phối hợp retrieval, tools và đánh giá chất lượng.",
        ],
        "tag": "Mở rộng",
        "tag_fill": PALETTE["purple"],
    },
]


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


def draw_lines(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    lines: list[str],
    fnt: ImageFont.FreeTypeFont,
    fill: str,
    gap: int = 8,
) -> int:
    x, y = xy
    cy = y
    for line in lines:
        draw.text((x, cy), line, font=fnt, fill=rgba(fill))
        cy += fnt.size + gap
    return cy


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    fnt: ImageFont.FreeTypeFont,
    fill: str,
    max_width: int,
    gap: int = 8,
) -> int:
    return draw_lines(draw, xy, wrap_pixels(text, fnt, max_width), fnt, fill, gap)


def fit_image(image: Image.Image, max_w: int, max_h: int) -> Image.Image:
    copy = image.copy()
    copy.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    return copy


def rounded_card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str, outline: str, radius: int = 26) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=rgba(fill), outline=rgba(outline), width=3)


def load_diagrams() -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for spec in DIAGRAMS:
        path = PACK_DIR / spec["filename"]
        if not path.exists():
            raise FileNotFoundError(f"Thiếu ảnh sơ đồ: {path}")
        items.append({**spec, "path": path, "image": Image.open(path).convert("RGB")})
    return items


def build_a4_overview(items: list[dict[str, object]]) -> tuple[Path, Path]:
    img = Image.new("RGBA", (A4_W, A4_H), rgba(PALETTE["bg"]))
    draw = ImageDraw.Draw(img)

    title_font = font(64, True)
    subtitle_font = font(28)
    card_title_font = font(32, True)
    body_font = font(24)
    bullet_font = font(23)
    tag_font = font(20, True)

    draw.text((120, 90), "Bộ sơ đồ RAG và AI Agent", font=title_font, fill=rgba(PALETTE["ink"]))
    draw_wrapped(
        draw,
        (120, 182),
        "Trang tổng hợp này gộp 4 sơ đồ theo hai phong cách khác nhau để chèn trực tiếp vào báo cáo, đồ án hoặc thuyết trình.",
        subtitle_font,
        PALETTE["muted"],
        1880,
        10,
    )

    margin_x = 120
    gutter_x = 70
    gutter_y = 64
    card_w = (A4_W - 2 * margin_x - gutter_x) // 2
    card_h = 1320
    top_y = 310

    positions = [
        (margin_x, top_y),
        (margin_x + card_w + gutter_x, top_y),
        (margin_x, top_y + card_h + gutter_y),
        (margin_x + card_w + gutter_x, top_y + card_h + gutter_y),
    ]

    for spec, (x, y) in zip(items, positions):
        rounded_card(draw, (x, y, x + card_w, y + card_h), PALETTE["card"], PALETTE["border"])
        tag_w = 170
        draw.rounded_rectangle(
            (x + 34, y + 30, x + 34 + tag_w, y + 30 + 44),
            radius=22,
            fill=rgba(str(spec["tag_fill"])),
            outline=rgba(PALETTE["border"]),
            width=2,
        )
        tag_text = str(spec["tag"])
        tag_x = x + 34 + (tag_w - int(tag_font.getlength(tag_text))) // 2
        draw.text((tag_x, y + 42), tag_text, font=tag_font, fill=rgba(PALETTE["ink"]))

        draw_wrapped(draw, (x + 34, y + 98), str(spec["title"]), card_title_font, PALETTE["ink"], card_w - 68, 8)

        image_top = y + 178
        preview = fit_image(spec["image"], card_w - 70, 560)  # type: ignore[arg-type]
        preview_x = x + (card_w - preview.width) // 2
        preview_y = image_top + (560 - preview.height) // 2
        draw.rounded_rectangle(
            (x + 28, image_top - 6, x + card_w - 28, image_top + 566),
            radius=22,
            fill=rgba("#fbfdff"),
            outline=rgba(PALETTE["soft"]),
            width=2,
        )
        img.paste(preview, (preview_x, preview_y))

        cy = image_top + 600
        cy = draw_wrapped(draw, (x + 34, cy), str(spec["summary"]), body_font, PALETTE["muted"], card_w - 68, 10)
        cy += 18
        for bullet in spec["bullets"]:  # type: ignore[union-attr]
            bullet_lines = wrap_pixels("• " + bullet, bullet_font, card_w - 68)
            cy = draw_lines(draw, (x + 34, cy), bullet_lines, bullet_font, PALETTE["ink"], 7) + 10

    footer = "Các file nguồn ảnh nằm trong reports/generated/diagram_pack_vi và đã được tối ưu để dùng lại cho PowerPoint."
    draw_wrapped(draw, (120, 3370), footer, font(22), PALETTE["muted"], 2200, 6)

    png_path = PACK_DIR / "diagram_pack_a4_tong_hop.png"
    pdf_path = PACK_DIR / "diagram_pack_a4_tong_hop.pdf"
    img.convert("RGB").save(png_path, quality=95)
    img.convert("RGB").save(pdf_path, resolution=300.0)
    return png_path, pdf_path


def build_slide_images(items: list[dict[str, object]]) -> list[Path]:
    slide_paths: list[Path] = []

    title = Image.new("RGBA", (SLIDE_W, SLIDE_H), rgba(PALETTE["bg"]))
    draw = ImageDraw.Draw(title)
    rounded_card(draw, (90, 90, 1830, 990), PALETTE["card"], PALETTE["border"], 30)
    draw.text((140, 150), "Bộ sơ đồ RAG và AI Agent", font=font(50, True), fill=rgba(PALETTE["ink"]))
    draw_wrapped(
        draw,
        (140, 250),
        "Bộ slide này gói sẵn 4 sơ đồ đã vẽ, mỗi sơ đồ đi kèm giải thích ngắn để trình bày trực tiếp trong buổi báo cáo.",
        font(28),
        PALETTE["muted"],
        760,
        10,
    )
    draw_wrapped(
        draw,
        (140, 430),
        "Nội dung gồm: RAG cơ bản, pipeline nạp dữ liệu và truy xuất, Agent + RAG + công cụ bên ngoài, và Agentic RAG mở rộng.",
        font(28),
        PALETTE["ink"],
        760,
        10,
    )
    a4_preview = fit_image(Image.open(PACK_DIR / "diagram_pack_a4_tong_hop.png").convert("RGB"), 760, 760)
    title.paste(a4_preview, (980 + (760 - a4_preview.width) // 2, 170 + (760 - a4_preview.height) // 2))
    title_path = SLIDES_DIR / "slide_00_bia.png"
    title.convert("RGB").save(title_path, quality=95)
    slide_paths.append(title_path)

    for idx, spec in enumerate(items, start=1):
        slide = Image.new("RGBA", (SLIDE_W, SLIDE_H), rgba(PALETTE["bg"]))
        draw = ImageDraw.Draw(slide)
        rounded_card(draw, (60, 60, 1860, 1020), PALETTE["card"], PALETTE["border"], 28)
        draw.rounded_rectangle((80, 80, 1840, 160), radius=18, fill=rgba(PALETTE["soft"]), outline=rgba(PALETTE["border"]), width=2)
        draw.text((120, 100), str(spec["title"]), font=font(40, True), fill=rgba(PALETTE["ink"]))

        left_box = (100, 210, 760, 950)
        right_box = (790, 210, 1780, 950)
        rounded_card(draw, left_box, "#fbfdff", PALETTE["soft"], 24)
        rounded_card(draw, right_box, "#fbfdff", PALETTE["soft"], 24)

        tag_fill = str(spec["tag_fill"])
        draw.rounded_rectangle((130, 245, 310, 290), radius=22, fill=rgba(tag_fill), outline=rgba(PALETTE["border"]), width=2)
        tag_text = str(spec["tag"])
        draw.text((130 + (180 - int(font(20, True).getlength(tag_text))) // 2, 257), tag_text, font=font(20, True), fill=rgba(PALETTE["ink"]))

        cy = draw_wrapped(draw, (130, 325), str(spec["summary"]), font(28), PALETTE["ink"], 600, 10)
        cy += 26
        for bullet in spec["bullets"]:  # type: ignore[union-attr]
            bullet_lines = wrap_pixels("• " + bullet, font(25), 600)
            cy = draw_lines(draw, (130, cy), bullet_lines, font(25), PALETTE["muted"], 8) + 14

        note = "Dùng tốt cho slide thuyết trình, báo cáo Word hoặc phần mô tả kiến trúc trong đồ án."
        draw_wrapped(draw, (130, 760), note, font(24), PALETTE["accent"], 600, 8)

        preview = fit_image(spec["image"], right_box[2] - right_box[0] - 48, right_box[3] - right_box[1] - 48)  # type: ignore[arg-type]
        paste_x = right_box[0] + (right_box[2] - right_box[0] - preview.width) // 2
        paste_y = right_box[1] + (right_box[3] - right_box[1] - preview.height) // 2
        slide.paste(preview, (paste_x, paste_y))

        slide_path = SLIDES_DIR / f"slide_{idx:02d}.png"
        slide.convert("RGB").save(slide_path, quality=95)
        slide_paths.append(slide_path)

    return slide_paths


def build_pptx(slide_paths: list[Path]) -> Path:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    slide_count = len(slide_paths)
    out_path = PACK_DIR / "diagram_pack_slide_deck.pptx"

    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Default Extension="png" ContentType="image/png"/>',
        '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>',
        '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>',
        '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>',
        '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>',
        '<Override PartName="/ppt/presProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"/>',
        '<Override PartName="/ppt/viewProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"/>',
        '<Override PartName="/ppt/tableStyles.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"/>',
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>',
    ]
    for idx in range(1, slide_count + 1):
        content_types.append(
            f'<Override PartName="/ppt/slides/slide{idx}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        )
    content_types.append("</Types>")

    slide_titles = ["Bộ sơ đồ RAG và AI Agent"] + [str(spec["title"]) for spec in DIAGRAMS]
    titles_xml = "".join(f"<vt:lpstr>{escape(title)}</vt:lpstr>" for title in slide_titles[:slide_count])
    files = {
        "[Content_Types].xml": "".join(content_types),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
            "</Relationships>"
        ),
        "docProps/app.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
            "<Application>Codex</Application>"
            "<PresentationFormat>Widescreen</PresentationFormat>"
            f"<Slides>{slide_count}</Slides><Notes>0</Notes><HiddenSlides>0</HiddenSlides><MMClips>0</MMClips><ScaleCrop>false</ScaleCrop>"
            '<HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Slides</vt:lpstr></vt:variant>'
            f"<vt:variant><vt:i4>{slide_count}</vt:i4></vt:variant></vt:vector></HeadingPairs>"
            f'<TitlesOfParts><vt:vector size="{slide_count}" baseType="lpstr">{titles_xml}</vt:vector></TitlesOfParts>'
            "<Company>OpenAI Codex</Company><AppVersion>1.0</AppVersion></Properties>"
        ),
        "docProps/core.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            "<dc:title>Bộ sơ đồ RAG và AI Agent</dc:title>"
            "<dc:creator>Codex</dc:creator><cp:lastModifiedBy>Codex</cp:lastModifiedBy>"
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
            "</cp:coreProperties>"
        ),
        "ppt/presProps.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:presentationPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>'
        ),
        "ppt/viewProps.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:viewPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:normalViewPr/><p:slideViewPr scale="100000"/><p:gridSpacing cx="780288" cy="780288"/></p:viewPr>'
        ),
        "ppt/tableStyles.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>'
        ),
        "ppt/slideMasters/slideMaster1.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:cSld name="Blank Master"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/>'
            "<p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/>"
            "<a:ext cx=\"0\" cy=\"0\"/><a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm>"
            "</p:grpSpPr></p:spTree></p:cSld>"
            '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" '
            'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
            '<p:sldLayoutIdLst><p:sldLayoutId id="1" r:id="rId1"/></p:sldLayoutIdLst>'
            "<p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>"
        ),
        "ppt/slideMasters/_rels/slideMaster1.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>'
            "</Relationships>"
        ),
        "ppt/slideLayouts/slideLayout1.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">'
            '<p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
            "</p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/>"
            "<a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>"
            "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>"
        ),
        "ppt/slideLayouts/_rels/slideLayout1.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>'
            "</Relationships>"
        ),
        "ppt/theme/theme1.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Office">'
            '<a:themeElements><a:clrScheme name="Office">'
            '<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>'
            '<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
            '<a:dk2><a:srgbClr val="233042"/></a:dk2><a:lt2><a:srgbClr val="FFFFFF"/></a:lt2>'
            '<a:accent1><a:srgbClr val="325EA8"/></a:accent1><a:accent2><a:srgbClr val="E7F6E8"/></a:accent2>'
            '<a:accent3><a:srgbClr val="FFF1DB"/></a:accent3><a:accent4><a:srgbClr val="FDE6EE"/></a:accent4>'
            '<a:accent5><a:srgbClr val="EFEAFF"/></a:accent5><a:accent6><a:srgbClr val="CFDEF0"/></a:accent6>'
            '<a:hlink><a:srgbClr val="325EA8"/></a:hlink><a:folHlink><a:srgbClr val="325EA8"/></a:folHlink>'
            '</a:clrScheme><a:fontScheme name="Office"><a:majorFont><a:latin typeface="Segoe UI"/></a:majorFont>'
            '<a:minorFont><a:latin typeface="Segoe UI"/></a:minorFont></a:fontScheme>'
            '<a:fmtScheme name="Office"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
            '<a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>'
            '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
            '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>'
            "</a:fmtScheme></a:themeElements></a:theme>"
        ),
    }

    sld_ids = []
    rels = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>',
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps" Target="presProps.xml"/>',
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps" Target="viewProps.xml"/>',
        '<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles" Target="tableStyles.xml"/>',
    ]

    for idx, slide_path in enumerate(slide_paths, start=1):
        rel_id = idx + 4
        sld_ids.append(f'<p:sldId id="{255 + idx}" r:id="rId{rel_id}"/>')
        rels.append(
            f'<Relationship Id="rId{rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{idx}.xml"/>'
        )
        image_name = slide_path.name
        slide_title = escape(slide_titles[idx - 1] if idx - 1 < len(slide_titles) else f"Slide {idx}")
        files[f"ppt/slides/slide{idx}.xml"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            f'<p:cSld name="{slide_title}"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/>'
            "<p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/>"
            "<a:ext cx=\"0\" cy=\"0\"/><a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr>"
            f'<p:pic><p:nvPicPr><p:cNvPr id="2" name="{escape(image_name)}"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
            '<p:blipFill><a:blip r:embed="rId2"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
            f'<p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{PPT_CX}" cy="{PPT_CY}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'
            "</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>"
        )
        files[f"ppt/slides/_rels/slide{idx}.xml.rels"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
            f'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{escape(image_name)}"/>'
            "</Relationships>"
        )

    rels.append("</Relationships>")
    files["ppt/_rels/presentation.xml.rels"] = "".join(rels)
    files["ppt/presentation.xml"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
        f"<p:sldIdLst>{''.join(sld_ids)}</p:sldIdLst>"
        f'<p:sldSz cx="{PPT_CX}" cy="{PPT_CY}"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>'
    )

    with ZipFile(out_path, "w", ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
        for slide_path in slide_paths:
            zf.write(slide_path, f"ppt/media/{slide_path.name}")

    return out_path


def clean_xml(text: str) -> str:
    return "".join(ch for ch in text if ch in "\t\n\r" or ord(ch) >= 32)


def para(text: str = "", style: str | None = None) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    if not text:
        return f"<w:p>{ppr}</w:p>"
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(clean_xml(text))}</w:t></w:r></w:p>'


def page_break() -> str:
    return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


def image_xml(rel_id: str, pic_id: int, name: str, cx: int, cy: int) -> str:
    return f"""
<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:drawing>
<wp:inline distT="0" distB="0" distL="0" distR="0">
<wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{pic_id}" name="{escape(name)}"/>
<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
<pic:pic><pic:nvPicPr><pic:cNvPr id="{pic_id}" name="{escape(name)}"/><pic:cNvPicPr/></pic:nvPicPr>
<pic:blipFill><a:blip r:embed="{rel_id}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>
</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>
"""


def build_docx(items: list[dict[str, object]], a4_png: Path) -> Path:
    images = [a4_png] + [spec["path"] for spec in items]  # type: ignore[list-item]
    rels: dict[str, tuple[str, str, int, int]] = {}
    rel_xml: list[str] = []
    media: list[tuple[Path, str]] = []

    for index, image_path in enumerate(images, start=1):
        rel_id = f"rId{index}"
        media_name = f"image{index}.png"
        with Image.open(image_path) as img:
            w, h = img.size
        cx = int(6.35 * EMU_PER_INCH)
        cy = int(cx * h / w)
        rels[str(image_path)] = (rel_id, media_name, cx, cy)
        rel_xml.append(
            f'<Relationship Id="{rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{media_name}"/>'
        )
        media.append((image_path, media_name))

    body: list[str] = [
        para("Bộ sơ đồ RAG và AI Agent", "Title"),
        para("Tài liệu này tổng hợp các sơ đồ đã vẽ theo phong cách báo cáo và có kèm diễn giải ngắn để chèn trực tiếp vào Word hoặc nộp báo cáo.", "Normal"),
        para("Phần đầu là ảnh tổng hợp A4, sau đó là từng sơ đồ riêng với ý nghĩa và gợi ý sử dụng.", "Normal"),
    ]
    rel_id, media_name, cx, cy = rels[str(a4_png)]
    body.append(image_xml(rel_id, 1, media_name, cx, cy))
    body.append(para("Hình tổng hợp 4 sơ đồ RAG và AI Agent.", "Caption"))
    body.append(page_break())

    pic_id = 2
    for idx, spec in enumerate(items, start=1):
        body.append(para(f"{idx}. {spec['title']}", "Heading1"))
        body.append(para(str(spec["summary"]), "Normal"))
        for bullet in spec["bullets"]:  # type: ignore[union-attr]
            body.append(para("• " + bullet, "ListParagraph"))
        body.append(para(f"Phân loại: {spec['tag']}.", "Heading2"))
        rel_id, media_name, cx, cy = rels[str(spec["path"])]  # type: ignore[index]
        body.append(image_xml(rel_id, pic_id, media_name, cx, cy))
        body.append(para(f"Hình {idx}: {spec['title']}.", "Caption"))
        if idx != len(items):
            body.append(page_break())
        pic_id += 1

    body.append(
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="900" w:right="900" w:bottom="900" w:left="900" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
    )

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    document = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><w:body>{''.join(body)}</w:body></w:document>"""
    styles = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr><w:rPr><w:rFonts w:ascii="Segoe UI" w:hAnsi="Segoe UI"/><w:sz w:val="22"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="220"/></w:pPr><w:rPr><w:rFonts w:ascii="Segoe UI" w:hAnsi="Segoe UI"/><w:b/><w:sz w:val="34"/><w:color w:val="233042"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="Heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="260" w:after="140"/></w:pPr><w:rPr><w:rFonts w:ascii="Segoe UI" w:hAnsi="Segoe UI"/><w:b/><w:sz w:val="28"/><w:color w:val="233042"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="Heading 2"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="120" w:after="80"/></w:pPr><w:rPr><w:rFonts w:ascii="Segoe UI" w:hAnsi="Segoe UI"/><w:b/><w:sz w:val="24"/><w:color w:val="526173"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="360" w:hanging="180"/><w:spacing w:after="90"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="Caption"/><w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/><w:spacing w:before="60" w:after="160"/></w:pPr><w:rPr><w:rFonts w:ascii="Segoe UI" w:hAnsi="Segoe UI"/><w:i/><w:sz w:val="20"/><w:color w:val="526173"/></w:rPr></w:style>
</w:styles>"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>"""
    doc_rels = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{''.join(rel_xml)}</Relationships>"""
    app = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Codex</Application></Properties>"""
    core = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>Bộ sơ đồ RAG và AI Agent</dc:title><dc:creator>Codex</dc:creator><cp:lastModifiedBy>Codex</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>"""

    output = PACK_DIR / "diagram_pack_thuyet_minh.docx"
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types)
        docx.writestr("_rels/.rels", root_rels)
        docx.writestr("docProps/app.xml", app)
        docx.writestr("docProps/core.xml", core)
        docx.writestr("word/document.xml", document)
        docx.writestr("word/styles.xml", styles)
        docx.writestr("word/_rels/document.xml.rels", doc_rels)
        for image_path, media_name in media:
            docx.write(image_path, f"word/media/{media_name}")
    return output


def build_notes_markdown() -> Path:
    lines = [
        "# Deliverables",
        "",
        "- `diagram_pack_a4_tong_hop.png`: bản tổng hợp A4 dạng ảnh.",
        "- `diagram_pack_a4_tong_hop.pdf`: bản tổng hợp A4 dạng PDF.",
        "- `diagram_pack_thuyet_minh.docx`: file Word có ảnh và phần giải thích.",
        "- `slides/`: ảnh slide cũ, giữ lại làm nguồn tham chiếu nếu cần.",
        "",
        "## Nội dung file DOCX",
        "",
        "1. Mở đầu và ảnh tổng hợp A4.",
        "2. RAG cơ bản.",
        "3. Nạp dữ liệu và truy xuất RAG.",
        "4. Agent + RAG + công cụ bên ngoài.",
        "5. Agentic RAG mở rộng.",
    ]
    path = PACK_DIR / "DELIVERABLES.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    items = load_diagrams()
    a4_png, a4_pdf = build_a4_overview(items)
    docx = build_docx(items, a4_png)
    notes = build_notes_markdown()
    for path in [a4_png, a4_pdf, docx, notes]:
        print(path)


if __name__ == "__main__":
    main()
