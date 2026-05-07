from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from textwrap import wrap
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageDraw, ImageFont

def _find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "main.py").exists() and (parent / "services").is_dir():
            return parent
    return Path(__file__).resolve().parents[2]


OUT = _find_repo_root() / 'reports' / 'generated' / 'ai_agent_diagrams'
OUT.mkdir(parents=True, exist_ok=True)

REG = r'C:\Windows\Fonts\segoeui.ttf'
BOLD = r'C:\Windows\Fonts\segoeuib.ttf'

C = {
    'bg': '#ffffff',
    'rag_bg': '#f3f7ff',
    'ink': '#2c3a86',
    'line': '#6271b8',
    'dash': '#8090c8',
    'orange_fill': '#ffefcf',
    'orange_stroke': '#f0c67b',
    'blue_fill': '#d8f0ff',
    'blue_stroke': '#9fd4ee',
    'green_fill': '#d8fadf',
    'green_stroke': '#97d89d',
    'pink_fill': '#ffe1eb',
    'pink_stroke': '#e5a4bd',
    'purple_fill': '#ebe6ff',
    'purple_stroke': '#b9abf0',
    'yellow_fill': '#fff0d4',
    'yellow_stroke': '#ecc384',
}

PNG_W = 1800
PNG_H = 1180
SVG_W = 1800
SVG_H = 1180
PPT_CX = 12192000
PPT_CY = 6858000


def rgba(color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    color = color.lstrip('#')
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(BOLD if bold else REG, size=size)


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


def draw_center_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, fnt: ImageFont.FreeTypeFont, fill: tuple[int, int, int, int], gap: int = 6) -> None:
    lines = wrap_pixels(text, fnt, box[2] - box[0] - 20)
    x1, y1, x2, y2 = box
    total_h = len(lines) * fnt.size + max(0, len(lines) - 1) * gap
    cy = y1 + (y2 - y1 - total_h) // 2
    for line in lines:
        w = int(fnt.getlength(line))
        cx = x1 + (x2 - x1 - w) // 2
        draw.text((cx, cy), line, font=fnt, fill=fill)
        cy += fnt.size + gap


def draw_box(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], text: str, fill: tuple[int, int, int, int], outline: tuple[int, int, int, int], title_font: ImageFont.FreeTypeFont) -> None:
    draw.rounded_rectangle(xy, radius=14, fill=fill, outline=outline, width=2)
    draw_center_text(draw, xy, text, title_font, (35, 35, 35, 255), 5)


def draw_arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], fill: tuple[int, int, int, int], width: int = 4, arrow_size: int = 12) -> None:
    draw.line([start, end], fill=fill, width=width)
    sx, sy = start
    ex, ey = end
    if abs(ex - sx) >= abs(ey - sy):
        d = 1 if ex >= sx else -1
        pts = [(ex, ey), (ex - arrow_size * d, ey - arrow_size // 2), (ex - arrow_size * d, ey + arrow_size // 2)]
    else:
        d = 1 if ey >= sy else -1
        pts = [(ex, ey), (ex - arrow_size // 2, ey - arrow_size * d), (ex + arrow_size // 2, ey - arrow_size * d)]
    draw.polygon(pts, fill=fill)


def draw_dashed_segment(draw: ImageDraw.ImageDraw, p1: tuple[int, int], p2: tuple[int, int], fill: tuple[int, int, int, int], width: int = 4, dash: int = 14, gap: int = 10) -> None:
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2:
        direction = 1 if y2 >= y1 else -1
        cur = y1
        while (cur - y2) * direction < 0:
            end = cur + dash * direction
            if (end - y2) * direction > 0:
                end = y2
            draw.line((x1, cur, x2, end), fill=fill, width=width)
            cur += (dash + gap) * direction
    elif y1 == y2:
        direction = 1 if x2 >= x1 else -1
        cur = x1
        while (cur - x2) * direction < 0:
            end = cur + dash * direction
            if (end - x2) * direction > 0:
                end = x2
            draw.line((cur, y1, end, y2), fill=fill, width=width)
            cur += (dash + gap) * direction


def draw_dashed_poly(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], fill: tuple[int, int, int, int], width: int = 4) -> None:
    for a, b in zip(points, points[1:]):
        draw_dashed_segment(draw, a, b, fill, width)


def svg_text(x: int, y: int, lines: list[str], size: int, fill: str, weight: str = '600', anchor: str = 'middle', line_height: int = 26) -> str:
    chunks = []
    for idx, line in enumerate(lines):
        dy = '0' if idx == 0 else str(line_height)
        chunks.append(f'<tspan x="{x}" dy="{dy}">{escape(line)}</tspan>')
    return f'<text x="{x}" y="{y}" font-family="Segoe UI" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}">{"".join(chunks)}</text>'


def svg_box(x: int, y: int, w: int, h: int, text: str, fill: str, stroke: str, size: int = 22) -> str:
    lines = wrap(text, width=16, break_long_words=False, break_on_hyphens=False) or [text]
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" stroke="{stroke}" stroke-width="2"/>' + svg_text(x + w // 2, y + h // 2 - (8 if len(lines) > 1 else 0), lines, size, '#232323')


def svg_arrow(x1: int, y1: int, x2: int, y2: int, dashed: bool = False) -> str:
    dash = ' stroke-dasharray="10 8"' if dashed else ''
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{C["line"]}" stroke-width="4"{dash} marker-end="url(#arrow)"/>'


def svg_poly(points: list[tuple[int, int]], dashed: bool = False) -> str:
    dash = ' stroke-dasharray="10 8"' if dashed else ''
    pts = ' '.join(f'{x},{y}' for x, y in points)
    return f'<polyline points="{pts}" fill="none" stroke="{C["dash"] if dashed else C["line"]}" stroke-width="4"{dash} marker-end="url(#arrow)"/>'

def build_png() -> Path:
    img = Image.new('RGBA', (PNG_W, PNG_H), rgba(C['bg']))
    draw = ImageDraw.Draw(img)
    title_font = font(26, True)
    box_font = font(20, True)
    tiny_font = font(18)
    small_font = font(16)
    line = rgba(C['line'])
    dash = rgba(C['dash'])

    draw.text((660, 26), 'RAG + AI Agent ecosystem for ICTU chatbot', font=title_font, fill=rgba(C['ink']))

    rag_panel = (390, 90, 1240, 590)
    draw.rounded_rectangle(rag_panel, radius=46, fill=rgba(C['rag_bg']), outline=rgba('#d9e4ff'), width=2)
    draw.text((445, 128), 'RAG', font=font(28, True), fill=rgba(C['ink']))

    query = (455, 300, 585, 360)
    emb_model = (470, 210, 660, 270)
    q_embed = (690, 120, 910, 180)
    vectordb = (960, 210, 1180, 270)
    candidates = (1080, 300, 1160, 430)
    prompt = (835, 435, 1035, 505)
    llm = (470, 440, 610, 500)

    draw_box(draw, query, 'Query', rgba(C['green_fill']), rgba(C['green_stroke']), box_font)
    draw_box(draw, emb_model, 'Embedding Model', rgba(C['blue_fill']), rgba(C['blue_stroke']), box_font)
    draw_box(draw, q_embed, 'Query Embedding', rgba(C['orange_fill']), rgba(C['orange_stroke']), box_font)
    draw_box(draw, vectordb, 'Vector Database', rgba(C['pink_fill']), rgba(C['pink_stroke']), box_font)
    draw_box(draw, prompt, 'Prompt with context', rgba(C['green_fill']), rgba(C['green_stroke']), box_font)
    draw_box(draw, llm, 'Gemini LLM', rgba(C['blue_fill']), rgba(C['blue_stroke']), box_font)

    for offset in (0, 10, 20):
        draw.rounded_rectangle((candidates[0] - offset, candidates[1] + offset, candidates[2] - offset, candidates[3] + offset), radius=12, fill=None, outline=rgba(C['yellow_stroke']), width=2)
    draw_center_text(draw, candidates, 'Candidates', box_font, (65, 65, 65, 255), 4)

    draw_dashed_poly(draw, [(585, 330), (720, 330), (720, 180)], dash)
    draw_dashed_poly(draw, [(565, 300), (565, 270), (565, 270)], dash)
    draw_dashed_poly(draw, [(660, 240), (710, 180), (690, 150)], dash)
    draw_dashed_poly(draw, [(910, 150), (980, 210)], dash)
    draw_arrow(draw, (1070, 270), (1115, 300), line)
    draw_dashed_poly(draw, [(1080, 360), (1035, 360), (1035, 470)], dash)
    draw_dashed_poly(draw, [(835, 470), (610, 470)], dash)
    draw_dashed_poly(draw, [(585, 330), (840, 470)], dash)

    user_x = 170
    user_y = 860
    draw.ellipse((user_x, user_y - 58, user_x + 44, user_y - 14), outline=rgba(C['ink']), width=4)
    draw.arc((user_x - 8, user_y - 10, user_x + 52, user_y + 50), 200, -20, fill=rgba(C['ink']), width=4)
    draw.text((160, 930), 'User', font=font(24, True), fill=(25, 25, 25, 255))

    agent = (620, 760, 920, 980)
    draw.rounded_rectangle(agent, radius=24, fill=rgba(C['orange_fill']), outline=rgba(C['orange_stroke']), width=3)
    draw.text((712, 810), 'AI Agent', font=font(28, True), fill=rgba(C['ink']))
    llm_inner = (705, 855, 835, 920)
    draw_box(draw, llm_inner, 'LLM(s)', rgba(C['blue_fill']), rgba(C['blue_stroke']), font(22, True))

    web_box = (1180, 700, 1530, 790)
    api_box = (1180, 855, 1530, 955)
    action_box = (1180, 1010, 1530, 1110)
    draw_box(draw, web_box, 'Web UI / Partner API', rgba(C['orange_fill']), rgba(C['orange_stroke']), font(22, True))
    draw_box(draw, api_box, 'School systems / External API', rgba(C['purple_fill']), rgba(C['purple_stroke']), font(22, True))
    draw_box(draw, action_box, 'Knowledge actions\nUpload / Approve / Index', rgba(C['pink_fill']), rgba(C['pink_stroke']), font(22, True))

    draw_dashed_poly(draw, [(260, 880), (620, 880)], dash)
    draw_dashed_poly(draw, [(620, 915), (260, 915)], dash)
    draw_dashed_poly(draw, [(770, 760), (770, 590)], dash)
    draw_arrow(draw, (770, 590), (770, 590 - 1), line)
    draw_dashed_poly(draw, [(920, 870), (1180, 745)], dash)
    draw_dashed_poly(draw, [(920, 900), (1180, 900)], dash)
    draw_dashed_poly(draw, [(920, 930), (1180, 1060)], dash)

    draw.text((472, 553), 'Query -> embedding -> retrieve candidates -> build grounded prompt -> LLM answer', font=tiny_font, fill=rgba(C['ink']))
    draw.text((610, 1018), 'The agent can call retrieval, APIs and knowledge operations around the main LLM.', font=small_font, fill=rgba('#5d6aa4'))

    out_path = OUT / 'rag_agent_ecosystem_style.png'
    img.convert('RGB').save(out_path)
    return out_path


def build_svg() -> Path:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_W}" height="{SVG_H}" viewBox="0 0 {SVG_W} {SVG_H}">']
    parts.append(f'<defs><marker id="arrow" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="{C["line"]}"/></marker></defs>')
    parts.append(f'<rect width="{SVG_W}" height="{SVG_H}" fill="{C["bg"]}"/>')
    parts.append(svg_text(900, 48, ['RAG + AI Agent ecosystem for ICTU chatbot'], 26, C['ink']))
    parts.append(f'<rect x="390" y="90" width="850" height="500" rx="46" fill="{C["rag_bg"]}" stroke="#d9e4ff" stroke-width="2"/>')
    parts.append(svg_text(465, 130, ['RAG'], 28, C['ink'], anchor='start'))
    parts.append(svg_box(455, 300, 130, 60, 'Query', C['green_fill'], C['green_stroke'], 20))
    parts.append(svg_box(470, 210, 190, 60, 'Embedding Model', C['blue_fill'], C['blue_stroke'], 20))
    parts.append(svg_box(690, 120, 220, 60, 'Query Embedding', C['orange_fill'], C['orange_stroke'], 20))
    parts.append(svg_box(960, 210, 220, 60, 'Vector Database', C['pink_fill'], C['pink_stroke'], 20))
    parts.append(svg_box(835, 435, 200, 70, 'Prompt with context', C['green_fill'], C['green_stroke'], 20))
    parts.append(svg_box(470, 440, 140, 60, 'Gemini LLM', C['blue_fill'], C['blue_stroke'], 20))
    for offset in (20, 10, 0):
        parts.append(f'<rect x="{1080 - offset}" y="{300 + offset}" width="80" height="130" rx="12" fill="none" stroke="{C["yellow_stroke"]}" stroke-width="2"/>')
    parts.append(svg_text(1120, 365, ['Candidates'], 20, '#444444'))
    parts.extend([
        svg_poly([(585, 330), (720, 330), (720, 180)], True),
        svg_poly([(660, 240), (710, 180), (690, 150)], True),
        svg_poly([(910, 150), (980, 210)], True),
        svg_arrow(1070, 270, 1115, 300),
        svg_poly([(1080, 360), (1035, 360), (1035, 470)], True),
        svg_poly([(835, 470), (610, 470)], True),
        svg_poly([(585, 330), (840, 470)], True),
    ])
    parts.append('<ellipse cx="192" cy="822" rx="22" ry="22" fill="none" stroke="#2c3a86" stroke-width="4"/>')
    parts.append('<path d="M 162 870 Q 192 835 222 870" fill="none" stroke="#2c3a86" stroke-width="4"/>')
    parts.append(svg_text(192, 935, ['User'], 24, '#202020'))
    parts.append(f'<rect x="620" y="760" width="300" height="220" rx="24" fill="{C["orange_fill"]}" stroke="{C["orange_stroke"]}" stroke-width="3"/>')
    parts.append(svg_text(770, 812, ['AI Agent'], 28, C['ink']))
    parts.append(svg_box(705, 855, 130, 65, 'LLM(s)', C['blue_fill'], C['blue_stroke'], 22))
    parts.append(svg_box(1180, 700, 350, 90, 'Web UI / Partner API', C['orange_fill'], C['orange_stroke'], 22))
    parts.append(svg_box(1180, 855, 350, 100, 'School systems / External API', C['purple_fill'], C['purple_stroke'], 22))
    parts.append(svg_box(1180, 1010, 350, 100, 'Knowledge actions Upload / Approve / Index', C['pink_fill'], C['pink_stroke'], 20))
    parts.extend([
        svg_poly([(260, 880), (620, 880)], True),
        svg_poly([(620, 915), (260, 915)], True),
        svg_poly([(770, 760), (770, 590)], True),
        svg_poly([(920, 870), (1180, 745)], True),
        svg_poly([(920, 900), (1180, 900)], True),
        svg_poly([(920, 930), (1180, 1060)], True),
    ])
    parts.append(svg_text(810, 555, ['Query -> embedding -> retrieve candidates -> build grounded prompt -> LLM answer'], 18, C['ink']))
    parts.append(svg_text(865, 1028, ['The agent can call retrieval, APIs and knowledge operations around the main LLM.'], 16, '#5d6aa4'))
    parts.append('</svg>')
    out_path = OUT / 'rag_agent_ecosystem_style.svg'
    out_path.write_text(''.join(parts), encoding='utf-8')
    return out_path


def build_pptx(image_path: Path) -> Path:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    out_path = OUT / 'rag_agent_ecosystem_style.pptx'
    image_name = image_path.name
    files = {
        '[Content_Types].xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/><Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/><Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/><Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/><Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/><Override PartName="/ppt/presProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"/><Override PartName="/ppt/viewProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"/><Override PartName="/ppt/tableStyles.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>''',
        '_rels/.rels': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>''',
        'docProps/app.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Codex</Application><PresentationFormat>Widescreen</PresentationFormat><Slides>1</Slides><TitlesOfParts><vt:vector size="1" baseType="lpstr"><vt:lpstr>RAG Agent Ecosystem</vt:lpstr></vt:vector></TitlesOfParts></Properties>''',
        'docProps/core.xml': f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>RAG Agent Ecosystem</dc:title><dc:creator>Codex</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>''',
        'ppt/presentation.xml': f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst><p:sldId id="256" r:id="rId5"/></p:sldIdLst><p:sldSz cx="{PPT_CX}" cy="{PPT_CY}"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>''',
        'ppt/_rels/presentation.xml.rels': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps" Target="presProps.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps" Target="viewProps.xml"/><Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles" Target="tableStyles.xml"/><Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/></Relationships>''',
        'ppt/presProps.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:presentationPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>''',
        'ppt/viewProps.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:viewPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:normalViewPr/><p:slideViewPr scale="100000"/></p:viewPr>''',
        'ppt/tableStyles.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>''',
        'ppt/slideMasters/slideMaster1.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld><p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/><p:sldLayoutIdLst><p:sldLayoutId id="1" r:id="rId1"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>''',
        'ppt/slideMasters/_rels/slideMaster1.xml.rels': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/></Relationships>''',
        'ppt/slideLayouts/slideLayout1.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1"><p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>''',
        'ppt/slideLayouts/_rels/slideLayout1.xml.rels': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>''',
        'ppt/theme/theme1.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Office"><a:themeElements><a:clrScheme name="Office"><a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1><a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1><a:accent1><a:srgbClr val="6271B8"/></a:accent1><a:accent2><a:srgbClr val="FFEFcf"/></a:accent2><a:accent3><a:srgbClr val="D8F0FF"/></a:accent3><a:accent4><a:srgbClr val="D8FADF"/></a:accent4><a:accent5><a:srgbClr val="FFE1EB"/></a:accent5><a:accent6><a:srgbClr val="EBE6FF"/></a:accent6><a:hlink><a:srgbClr val="6271B8"/></a:hlink><a:folHlink><a:srgbClr val="6271B8"/></a:folHlink></a:clrScheme><a:fontScheme name="Office"><a:majorFont><a:latin typeface="Segoe UI"/></a:majorFont><a:minorFont><a:latin typeface="Segoe UI"/></a:minorFont></a:fontScheme><a:fmtScheme name="Office"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst><a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst></a:fmtScheme></a:themeElements></a:theme>''',
        'ppt/slides/slide1.xml': f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld name="RAG Agent Ecosystem"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr><p:pic><p:nvPicPr><p:cNvPr id="2" name="{escape(image_name)}"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rId2"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{PPT_CX}" cy="{PPT_CY}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>''',
        'ppt/slides/_rels/slide1.xml.rels': f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{escape(image_name)}"/></Relationships>''',
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
