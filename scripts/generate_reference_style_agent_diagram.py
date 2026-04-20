from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from textwrap import wrap
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageDraw, ImageFont

OUT = Path(r'E:\new-test\reports\generated\ai_agent_diagrams')
OUT.mkdir(parents=True, exist_ok=True)

REG = r'C:\Windows\Fonts\segoeui.ttf'
BOLD = r'C:\Windows\Fonts\segoeuib.ttf'

COLORS = {
    'bg': '#ffffff',
    'ink': '#28307a',
    'soft_ink': '#4b558f',
    'box_fill': '#96cbef',
    'box_stroke': '#6aaedc',
    'line': '#31388c',
    'muted_fill': '#eaf4fb',
    'muted_stroke': '#bfdaf0',
}

SVG_W = 1800
SVG_H = 980
PNG_W = 1800
PNG_H = 980
PPT_CX = 12192000
PPT_CY = 6858000


def rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    color = hex_color.lstrip('#')
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(BOLD if bold else REG, size=size)


def wrap_chars(text: str, width: int) -> list[str]:
    return wrap(text, width=width, break_long_words=False, break_on_hyphens=False) or [text]


def wrap_pixels(text: str, fnt: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return ['']
    lines = [words[0]]
    for word in words[1:]:
        trial = lines[-1] + ' ' + word
        if fnt.getlength(trial) <= max_width:
            lines[-1] = trial
        else:
            lines.append(word)
    return lines


def svg_text(x: int, y: int, lines: list[str], size: int, fill: str, weight: str = '400', anchor: str = 'middle', line_height: int = 28) -> str:
    tspans = []
    for idx, line in enumerate(lines):
        dy = '0' if idx == 0 else str(line_height)
        tspans.append(f'<tspan x="{x}" dy="{dy}">{escape(line)}</tspan>')
    return f'<text x="{x}" y="{y}" font-family="Segoe UI" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}">{"".join(tspans)}</text>'


def svg_box(x: int, y: int, w: int, h: int, title: str, fill: str | None = None) -> str:
    fill = fill or COLORS['box_fill']
    cx = x + w // 2
    title_lines = wrap_chars(title, 18)
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="0" fill="{fill}" stroke="{COLORS["box_stroke"]}" stroke-width="1.5"/>'
        + svg_text(cx, y + h // 2 - (10 if len(title_lines) > 1 else 0), title_lines, 24, '#111111', '600', 'middle', 26)
    )


def svg_arrow(x1: int, y1: int, x2: int, y2: int, dashed: bool = False) -> str:
    dash = ' stroke-dasharray="10 8"' if dashed else ''
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{COLORS["line"]}" stroke-width="4"{dash} marker-end="url(#arrow)"/>'


def svg_poly(points: list[tuple[int, int]], dashed: bool = False) -> str:
    dash = ' stroke-dasharray="10 8"' if dashed else ''
    pts = ' '.join(f'{x},{y}' for x, y in points)
    return f'<polyline points="{pts}" fill="none" stroke="{COLORS["line"]}" stroke-width="4"{dash} marker-end="url(#arrow)"/>'


def svg_defs() -> str:
    return f'''
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="{COLORS['line']}"/>
      </marker>
    </defs>
    '''


def draw_center_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], lines: list[str], fnt: ImageFont.FreeTypeFont, fill: tuple[int, int, int, int], gap: int = 6) -> None:
    x1, y1, x2, y2 = box
    total_h = len(lines) * fnt.size + max(0, len(lines) - 1) * gap
    cy = y1 + (y2 - y1 - total_h) // 2
    for line in lines:
        w = int(fnt.getlength(line))
        cx = x1 + (x2 - x1 - w) // 2
        draw.text((cx, cy), line, font=fnt, fill=fill)
        cy += fnt.size + gap


def draw_arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], fill: tuple[int, int, int, int], width: int = 6) -> None:
    draw.line([start, end], fill=fill, width=width)
    sx, sy = start
    ex, ey = end
    if abs(ex - sx) >= abs(ey - sy):
        direction = 1 if ex >= sx else -1
        pts = [(ex, ey), (ex - 20 * direction, ey - 10), (ex - 20 * direction, ey + 10)]
    else:
        direction = 1 if ey >= sy else -1
        pts = [(ex, ey), (ex - 10, ey - 20 * direction), (ex + 10, ey - 20 * direction)]
    draw.polygon(pts, fill=fill)


def draw_dashed_line(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], fill: tuple[int, int, int, int], width: int = 4, dash: int = 14, gap: int = 10) -> None:
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if x1 == x2:
            step = dash + gap
            direction = 1 if y2 >= y1 else -1
            cur = y1
            while (cur - y2) * direction < 0:
                end = cur + dash * direction
                if (end - y2) * direction > 0:
                    end = y2
                draw.line((x1, cur, x2, end), fill=fill, width=width)
                cur += step * direction
        elif y1 == y2:
            step = dash + gap
            direction = 1 if x2 >= x1 else -1
            cur = x1
            while (cur - x2) * direction < 0:
                end = cur + dash * direction
                if (end - x2) * direction > 0:
                    end = x2
                draw.line((cur, y1, end, y2), fill=fill, width=width)
                cur += step * direction

def build_svg() -> Path:
    tool_boxes = [
        (80, 160, 260, 74, 'Sổ tay SV RAG'),
        (80, 268, 260, 74, 'Policy RAG'),
        (80, 376, 260, 74, 'FAQ / Thông báo'),
        (80, 484, 260, 74, 'Fallback Search'),
        (80, 592, 260, 74, '...Nguồn khác'),
    ]
    right_boxes = [
        (1450, 210, 290, 78, 'Router ý định'),
        (1450, 328, 290, 78, 'Clarification'),
        (1450, 446, 290, 78, 'Tự kiểm tra'),
        (1450, 564, 290, 78, 'Bộ test + độ đo'),
    ]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_W}" height="{SVG_H}" viewBox="0 0 {SVG_W} {SVG_H}">', svg_defs()]
    parts.append(f'<rect width="{SVG_W}" height="{SVG_H}" fill="{COLORS["bg"]}"/>')

    for box in tool_boxes:
        parts.append(svg_box(*box))
    for box in right_boxes:
        parts.append(svg_box(*box))

    parts.append(svg_box(520, 78, 210, 68, 'Ngắn hạn'))
    parts.append(svg_box(1040, 78, 210, 68, 'Dài hạn'))

    parts.append(svg_text(890, 160, ['Bộ nhớ'], 28, '#111111', '600'))
    parts.append(svg_text(610, 492, ['Tools'], 26, '#111111', '600'))
    parts.append(svg_text(898, 492, ['Agent'], 26, '#111111', '600'))
    parts.append(svg_text(1160, 492, ['Lập kế hoạch'], 26, '#111111', '600'))
    parts.append(svg_text(910, 835, ['Hành động'], 26, '#111111', '600'))
    parts.append(svg_text(900, 50, ['Kiến trúc AI Agent tổng thể theo style nghiên cứu'], 26, COLORS['soft_ink'], '600'))

    parts.append('<rect x="866" y="80" width="48" height="48" rx="8" fill="none" stroke="#31388c" stroke-width="5"/>')
    parts.append('<line x1="878" y1="72" x2="878" y2="80" stroke="#31388c" stroke-width="4"/>')
    parts.append('<line x1="890" y1="72" x2="890" y2="80" stroke="#31388c" stroke-width="4"/>')
    parts.append('<line x1="902" y1="72" x2="902" y2="80" stroke="#31388c" stroke-width="4"/>')
    parts.append('<line x1="878" y1="128" x2="878" y2="136" stroke="#31388c" stroke-width="4"/>')
    parts.append('<line x1="890" y1="128" x2="890" y2="136" stroke="#31388c" stroke-width="4"/>')
    parts.append('<line x1="902" y1="128" x2="902" y2="136" stroke="#31388c" stroke-width="4"/>')

    parts.append('<circle cx="910" cy="802" r="32" fill="none" stroke="#31388c" stroke-width="5"/>')
    parts.append('<line x1="896" y1="802" x2="922" y2="802" stroke="#31388c" stroke-width="5"/>')
    parts.append('<polyline points="913,790 926,802 913,814" fill="none" stroke="#31388c" stroke-width="5"/>')

    parts.append('<circle cx="610" cy="440" r="34" fill="none" stroke="#31388c" stroke-width="5"/>')
    parts.append('<line x1="594" y1="424" x2="626" y2="456" stroke="#31388c" stroke-width="5"/>')
    parts.append('<line x1="626" y1="424" x2="594" y2="456" stroke="#31388c" stroke-width="5"/>')

    parts.append('<circle cx="1160" cy="440" r="34" fill="none" stroke="#31388c" stroke-width="5"/>')
    parts.append('<circle cx="1146" cy="440" r="5" fill="#31388c"/>')
    parts.append('<circle cx="1160" cy="440" r="5" fill="#31388c"/>')
    parts.append('<circle cx="1174" cy="440" r="5" fill="#31388c"/>')
    parts.append('<line x1="1146" y1="455" x2="1174" y2="455" stroke="#31388c" stroke-width="4"/>')

    parts.append('<rect x="870" y="394" width="58" height="54" rx="10" fill="none" stroke="#31388c" stroke-width="5"/>')
    parts.append('<circle cx="888" cy="414" r="5" fill="#31388c"/>')
    parts.append('<circle cx="910" cy="414" r="5" fill="#31388c"/>')
    parts.append('<line x1="885" y1="432" x2="913" y2="432" stroke="#31388c" stroke-width="4"/>')
    parts.append('<line x1="899" y1="390" x2="899" y2="378" stroke="#31388c" stroke-width="4"/>')
    parts.append('<circle cx="899" cy="372" r="6" fill="#ff4d6d" stroke="#31388c" stroke-width="3"/>')

    parts.append(svg_arrow(865, 102, 730, 102))
    parts.append(svg_arrow(915, 102, 1040, 102))
    parts.append(svg_arrow(899, 360, 899, 178))
    parts.append(svg_arrow(864, 440, 650, 440))
    parts.append(svg_arrow(930, 440, 1126, 440))
    parts.append(svg_arrow(899, 448, 899, 760))

    parts.append(svg_poly([(1128, 440), (1350, 440), (1350, 248), (1450, 248)]))
    parts.append(svg_poly([(1128, 440), (1350, 440), (1350, 366), (1450, 366)]))
    parts.append(svg_poly([(1128, 440), (1350, 440), (1350, 484), (1450, 484)]))
    parts.append(svg_poly([(1128, 440), (1350, 440), (1350, 602), (1450, 602)]))
    parts.append(svg_poly([(899, 172), (899, 190), (1160, 190), (1160, 406)], True))
    parts.append(svg_poly([(1160, 190), (1450, 190), (1450, 248)], True))

    parts.append('<line x1="390" y1="200" x2="390" y2="630" stroke="#31388c" stroke-width="4"/>')
    for _, y, w, h, _ in tool_boxes:
        cy = y + h // 2
        parts.append(svg_arrow(390, cy, 340, cy))
    parts.append(svg_arrow(850, 440, 390, 440))
    parts.append(svg_poly([(610, 474), (610, 730), (878, 730), (878, 802)], True))

    parts.append('</svg>')
    out_path = OUT / 'ai_agent_reference_style.svg'
    out_path.write_text(''.join(parts), encoding='utf-8')
    return out_path

def build_png() -> Path:
    image = Image.new('RGBA', (PNG_W, PNG_H), rgba(COLORS['bg']))
    draw = ImageDraw.Draw(image)
    title_font = font(24, True)
    box_font = font(22, True)
    label_font = font(22, True)
    small_font = font(18)
    line_color = rgba(COLORS['line'])

    draw.text((530, 24), 'Kiến trúc AI Agent tổng thể theo style nghiên cứu', font=title_font, fill=rgba(COLORS['soft_ink']))

    tool_boxes = [
        (80, 160, 260, 74, 'Sổ tay SV RAG'),
        (80, 268, 260, 74, 'Policy RAG'),
        (80, 376, 260, 74, 'FAQ / Thông báo'),
        (80, 484, 260, 74, 'Fallback Search'),
        (80, 592, 260, 74, '...Nguồn khác'),
    ]
    right_boxes = [
        (1450, 210, 290, 78, 'Router ý định'),
        (1450, 328, 290, 78, 'Clarification'),
        (1450, 446, 290, 78, 'Tự kiểm tra'),
        (1450, 564, 290, 78, 'Bộ test + độ đo'),
    ]
    top_boxes = [
        (520, 78, 210, 68, 'Ngắn hạn'),
        (1040, 78, 210, 68, 'Dài hạn'),
    ]

    for x, y, w, h, title in tool_boxes + right_boxes + top_boxes:
        draw.rectangle((x, y, x + w, y + h), fill=rgba(COLORS['box_fill']), outline=rgba(COLORS['box_stroke']), width=2)
        draw_center_text(draw, (x, y, x + w, y + h), wrap_pixels(title, box_font, w - 24), box_font, (17, 17, 17, 255), 4)

    draw.text((835, 146), 'Bộ nhớ', font=label_font, fill=(17, 17, 17, 255))
    draw.text((560, 478), 'Tools', font=label_font, fill=(17, 17, 17, 255))
    draw.text((860, 478), 'Agent', font=label_font, fill=(17, 17, 17, 255))
    draw.text((1070, 478), 'Lập kế hoạch', font=label_font, fill=(17, 17, 17, 255))
    draw.text((848, 835), 'Hành động', font=label_font, fill=(17, 17, 17, 255))

    draw.rounded_rectangle((866, 80, 914, 128), radius=8, outline=line_color, width=5)
    for x in (878, 890, 902):
        draw.line((x, 72, x, 80), fill=line_color, width=4)
        draw.line((x, 128, x, 136), fill=line_color, width=4)

    draw.ellipse((578, 408, 646, 476), outline=line_color, width=5)
    draw.line((594, 424, 626, 456), fill=line_color, width=5)
    draw.line((626, 424, 594, 456), fill=line_color, width=5)

    draw.ellipse((1126, 408, 1194, 476), outline=line_color, width=5)
    for cx in (1146, 1160, 1174):
        draw.ellipse((cx - 5, 435, cx + 5, 445), fill=line_color)
    draw.line((1146, 455, 1174, 455), fill=line_color, width=4)

    draw.rounded_rectangle((870, 394, 928, 448), radius=10, outline=line_color, width=5)
    for cx in (888, 910):
        draw.ellipse((cx - 5, 409, cx + 5, 419), fill=line_color)
    draw.line((885, 432, 913, 432), fill=line_color, width=4)
    draw.line((899, 390, 899, 378), fill=line_color, width=4)
    draw.ellipse((893, 366, 905, 378), fill=(255, 77, 109, 255), outline=line_color, width=3)

    draw.ellipse((878, 770, 942, 834), outline=line_color, width=5)
    draw.line((896, 802, 922, 802), fill=line_color, width=5)
    draw.line((913, 790, 926, 802), fill=line_color, width=5)
    draw.line((913, 814, 926, 802), fill=line_color, width=5)

    draw_arrow(draw, (865, 102), (730, 102), line_color)
    draw_arrow(draw, (915, 102), (1040, 102), line_color)
    draw_arrow(draw, (899, 360), (899, 178), line_color)
    draw_arrow(draw, (864, 440), (650, 440), line_color)
    draw_arrow(draw, (930, 440), (1126, 440), line_color)
    draw_arrow(draw, (899, 448), (899, 760), line_color)

    draw.line((1128, 440, 1350, 440), fill=line_color, width=6)
    draw.line((1350, 248, 1350, 602), fill=line_color, width=6)
    for y in (248, 366, 484, 602):
        draw_arrow(draw, (1350, y), (1450, y), line_color)

    draw_dashed_line(draw, [(899, 172), (899, 190), (1160, 190), (1160, 406)], line_color)
    draw_arrow(draw, (1160, 190), (1450, 248), line_color)

    draw.line((390, 200, 390, 630), fill=line_color, width=6)
    for _, y, _, h, _ in tool_boxes:
        cy = y + h // 2
        draw_arrow(draw, (390, cy), (340, cy), line_color)
    draw_arrow(draw, (850, 440), (390, 440), line_color)
    draw_dashed_line(draw, [(610, 474), (610, 730), (878, 730), (878, 802)], line_color)

    draw.text((80, 920), 'Bố cục lấy cảm hứng từ sơ đồ research: Tools - Agent - Memory - Planning - Action.', font=small_font, fill=rgba(COLORS['soft_ink']))

    out_path = OUT / 'ai_agent_reference_style.png'
    image.convert('RGB').save(out_path)
    return out_path

def build_pptx(image_path: Path) -> Path:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    image_name = image_path.name
    out_path = OUT / 'ai_agent_reference_style.pptx'
    files = {
        '[Content_Types].xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/><Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/><Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/><Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/><Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/><Override PartName="/ppt/presProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"/><Override PartName="/ppt/viewProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"/><Override PartName="/ppt/tableStyles.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>''',
        '_rels/.rels': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>''',
        'docProps/app.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Codex</Application><PresentationFormat>Widescreen</PresentationFormat><Slides>1</Slides><Notes>0</Notes><HiddenSlides>0</HiddenSlides><MMClips>0</MMClips><ScaleCrop>false</ScaleCrop><HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Slides</vt:lpstr></vt:variant><vt:variant><vt:i4>1</vt:i4></vt:variant></vt:vector></HeadingPairs><TitlesOfParts><vt:vector size="1" baseType="lpstr"><vt:lpstr>AI Agent Reference Style</vt:lpstr></vt:vector></TitlesOfParts><Company>OpenAI Codex</Company><AppVersion>1.0</AppVersion></Properties>''',
        'docProps/core.xml': f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>AI Agent Reference Style</dc:title><dc:creator>Codex</dc:creator><cp:lastModifiedBy>Codex</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>''',
        'ppt/presentation.xml': f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst><p:sldId id="256" r:id="rId5"/></p:sldIdLst><p:sldSz cx="{PPT_CX}" cy="{PPT_CY}"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>''',
        'ppt/_rels/presentation.xml.rels': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps" Target="presProps.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps" Target="viewProps.xml"/><Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles" Target="tableStyles.xml"/><Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/></Relationships>''',
        'ppt/presProps.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<p:presentationPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>''',
        'ppt/viewProps.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<p:viewPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:normalViewPr/><p:slideViewPr scale="100000"/><p:gridSpacing cx="780288" cy="780288"/></p:viewPr>''',
        'ppt/tableStyles.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>''',
        'ppt/slideMasters/slideMaster1.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld name="Blank Master"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld><p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/><p:sldLayoutIdLst><p:sldLayoutId id="1" r:id="rId1"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>''',
        'ppt/slideMasters/_rels/slideMaster1.xml.rels': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/></Relationships>''',
        'ppt/slideLayouts/slideLayout1.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1"><p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>''',
        'ppt/slideLayouts/_rels/slideLayout1.xml.rels': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>''',
        'ppt/theme/theme1.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Office"><a:themeElements><a:clrScheme name="Office"><a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1><a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="1F2937"/></a:dk2><a:lt2><a:srgbClr val="FFFFFF"/></a:lt2><a:accent1><a:srgbClr val="31388C"/></a:accent1><a:accent2><a:srgbClr val="96CBEF"/></a:accent2><a:accent3><a:srgbClr val="BFDaf0"/></a:accent3><a:accent4><a:srgbClr val="4B558F"/></a:accent4><a:accent5><a:srgbClr val="6AAEDC"/></a:accent5><a:accent6><a:srgbClr val="A0AEC0"/></a:accent6><a:hlink><a:srgbClr val="31388C"/></a:hlink><a:folHlink><a:srgbClr val="31388C"/></a:folHlink></a:clrScheme><a:fontScheme name="Office"><a:majorFont><a:latin typeface="Segoe UI"/></a:majorFont><a:minorFont><a:latin typeface="Segoe UI"/></a:minorFont></a:fontScheme><a:fmtScheme name="Office"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst><a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst></a:fmtScheme></a:themeElements></a:theme>''',
        'ppt/slides/slide1.xml': f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld name="AI Agent Reference Style"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr><p:pic><p:nvPicPr><p:cNvPr id="2" name="{escape(image_name)}"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rId2"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{PPT_CX}" cy="{PPT_CY}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>''',
        'ppt/slides/_rels/slide1.xml.rels': f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{escape(image_name)}"/></Relationships>''',
    }
    with ZipFile(out_path, 'w', ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
        zf.write(image_path, f'ppt/media/{image_name}')
    return out_path


def main() -> None:
    svg_path = build_svg()
    png_path = build_png()
    pptx_path = build_pptx(png_path)
    for path in (svg_path, png_path, pptx_path):
        print(path)


if __name__ == '__main__':
    main()
