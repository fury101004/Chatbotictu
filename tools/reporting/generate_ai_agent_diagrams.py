from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from textwrap import wrap
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

from PIL import Image, ImageDraw, ImageFont

def _find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "main.py").exists() and (parent / "services").is_dir():
            return parent
    return Path(__file__).resolve().parents[2]


out = _find_repo_root() / 'reports' / 'generated' / 'ai_agent_diagrams'
out.mkdir(parents=True, exist_ok=True)

REG = r'C:\Windows\Fonts\segoeui.ttf'
BOLD = r'C:\Windows\Fonts\segoeuib.ttf'
C = {
    'navy': '#0f172a', 'muted': '#475569', 'soft': '#64748b', 'sky': '#0ea5e9', 'emerald': '#10b981',
    'amber': '#f59e0b', 'orange': '#f97316', 'line': '#cbd5e1', 'white': '#ffffff', 'blue_fill': '#e0f2fe',
    'green_fill': '#dcfce7', 'amber_fill': '#fef3c7', 'orange_fill': '#ffedd5', 'slate_fill': '#f1f5f9'
}


def rgba(hex_color, alpha=255):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4)) + (alpha,)


def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else REG, size=size)


def wrap_chars(text, width):
    return wrap(text, width=width, break_long_words=False, break_on_hyphens=False) or [text]


def wrap_pixels(text, fnt, max_width):
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


def svg_defs():
    return f'''
    <defs>
      <linearGradient id="bgMain" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#f8fbff"/>
        <stop offset="50%" stop-color="#eef7ff"/>
        <stop offset="100%" stop-color="#f8fafc"/>
      </linearGradient>
      <linearGradient id="banner" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="{C['navy']}"/>
        <stop offset="100%" stop-color="#1d4ed8"/>
      </linearGradient>
      <filter id="shadow" x="-10%" y="-10%" width="130%" height="140%">
        <feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="#0f172a" flood-opacity="0.10"/>
      </filter>
      <marker id="arrow" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#2563eb"/>
      </marker>
      <marker id="arrowOrange" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="{C['orange']}"/>
      </marker>
    </defs>
    '''


def svg_text(x, y, lines, size, fill, weight='400', anchor='start', line_height=28):
    tspans = []
    for idx, line in enumerate(lines):
        dy = '0' if idx == 0 else str(line_height)
        tspans.append(f'<tspan x="{x}" dy="{dy}">{escape(line)}</tspan>')
    return f'<text x="{x}" y="{y}" font-family="Segoe UI" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{"".join(tspans)}</text>'


def svg_card(x, y, w, h, title, lines, fill, stroke, dashed=False, align='left'):
    dash = ' stroke-dasharray="12 8"' if dashed else ''
    text_x = x + 24 if align == 'left' else x + w // 2
    anchor = 'start' if align == 'left' else 'middle'
    title_lines = wrap_chars(title, 22 if align == 'center' else 24)
    body = []
    for line in lines:
        body.extend(wrap_chars(line, 30 if align == 'center' else 34))
    rect = f'<g filter="url(#shadow)"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="22" fill="{fill}" stroke="{stroke}" stroke-width="2.5"{dash}/></g>'
    return rect + svg_text(text_x, y + 38, title_lines, 24, C['navy'], '700', anchor) + svg_text(text_x, y + 76, body, 18, C['muted'], '400', anchor, 24)


def svg_arrow(x1, y1, x2, y2, color='#2563eb', dashed=False):
    dash = ' stroke-dasharray="10 8"' if dashed else ''
    marker = 'arrowOrange' if color == C['orange'] else 'arrow'
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="4"{dash} marker-end="url(#{marker})"/>'


def svg_polyline(points, color='#2563eb', dashed=False):
    dash = ' stroke-dasharray="10 8"' if dashed else ''
    marker = 'arrowOrange' if color == C['orange'] else 'arrow'
    point_str = ' '.join(f'{x},{y}' for x, y in points)
    return f'<polyline points="{point_str}" fill="none" stroke="{color}" stroke-width="4"{dash} marker-end="url(#{marker})"/>'


def svg_chip(x, y, w, text, fill, stroke, text_fill):
    return f'<rect x="{x}" y="{y}" width="{w}" height="42" rx="21" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>' + svg_text(x + 20, y + 28, [text], 17, text_fill, '600')


def overview_svg():
    W, H = 1600, 980
    cards = [
        svg_card(80, 180, 180, 98, 'Người dùng / Bài toán', ['Câu hỏi, tác vụ, mục tiêu'], C['white'], C['line']),
        svg_card(310, 180, 190, 98, 'Agent 1: Input + Normalizer', ['Chuẩn hóa đầu vào', 'gắn session, ngôn ngữ'], C['blue_fill'], C['sky']),
        svg_card(550, 180, 190, 98, 'Agent 2: Guardrail', ['Lọc nội dung xấu', 'trả lời nhanh lời chào'], C['green_fill'], C['emerald']),
        svg_card(790, 180, 190, 98, 'Agent 3: Router', ['Chọn nhánh tri thức', 'đúng tool RAG'], C['amber_fill'], C['amber']),
        svg_card(1210, 355, 280, 102, 'Agent 5: Response Composer', ['Tổng hợp ngữ cảnh', 'sinh phản hồi đa ngôn ngữ'], C['orange_fill'], C['orange']),
        svg_card(1210, 500, 280, 94, 'Session Memory + Logging', ['Lưu lịch sử, nguồn, retrieved ids'], C['slate_fill'], C['muted']),
        svg_card(1210, 635, 280, 94, 'API / Web UI', ['Trả kết quả về ứng dụng'], C['blue_fill'], C['sky']),
        svg_card(60, 355, 170, 260, 'Nguồn tri thức', ['Sổ tay sinh viên', 'Văn bản, quy định', 'FAQ, thông báo', 'Vector store, metadata'], C['slate_fill'], C['line']),
        svg_card(280, 355, 200, 110, 'Agent 4A: Handbook RAG', ['Tra cứu sổ tay sinh viên'], C['white'], C['sky']),
        svg_card(520, 355, 200, 110, 'Agent 4B: Policy RAG', ['Tra cứu văn bản, quy định'], C['white'], C['emerald']),
        svg_card(760, 355, 200, 110, 'Agent 4C: FAQ RAG', ['Tra cứu FAQ, thông báo'], C['white'], C['amber']),
        svg_card(1000, 355, 160, 110, 'Agent 4D: Fallback RAG', ['Gom nhiều nhóm khi câu hỏi mơ hồ'], C['white'], C['orange']),
        svg_card(70, 780, 450, 150, 'Bộ dữ liệu test', ['- Dataset câu hỏi chuẩn theo nhóm nghiệp vụ', '- expected_tool và expected_source', '- test router, retrieval, response'], C['white'], C['line']),
        svg_card(575, 780, 450, 150, 'Độ đo đánh giá', ['- Router accuracy và confusion matrix', '- hit@k, top-1 hit rate, MRR, latency', '- faithfulness, groundedness, pass rate'], C['white'], C['line']),
        svg_card(1080, 780, 450, 150, 'Triển khai thử nghiệm dần từng agent', ['GĐ1 hoàn thiện pipeline hiện tại', 'GĐ2 thêm Clarification Agent', 'GĐ3 thêm Ingestion Agent', 'GĐ4 thêm Evaluation Agent'], C['white'], C['orange'], True),
    ]
    arrows = [
        svg_arrow(260, 229, 310, 229), svg_arrow(500, 229, 550, 229), svg_arrow(740, 229, 790, 229),
        svg_polyline([(885, 278), (885, 320), (380, 320), (380, 355)]),
        svg_polyline([(885, 278), (885, 320), (620, 320), (620, 355)]),
        svg_polyline([(885, 278), (885, 320), (860, 320), (860, 355)]),
        svg_polyline([(885, 278), (885, 320), (1080, 320), (1080, 355)]),
        svg_arrow(230, 410, 280, 410), svg_arrow(230, 450, 520, 410), svg_arrow(230, 490, 760, 410), svg_arrow(230, 530, 1000, 410),
        svg_arrow(480, 410, 1210, 406), svg_arrow(720, 410, 1210, 406), svg_arrow(960, 410, 1210, 406), svg_arrow(1160, 410, 1210, 406),
        svg_arrow(1350, 457, 1350, 500), svg_arrow(1350, 594, 1350, 635),
        svg_polyline([(1305, 780), (1305, 745), (1350, 745), (1350, 729)], C['orange'], True),
        svg_polyline([(800, 780), (800, 742), (1350, 742), (1350, 729)], '#2563eb'),
    ]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">', svg_defs()]
    parts += [
        f'<rect width="{W}" height="{H}" fill="url(#bgMain)"/>',
        '<circle cx="1400" cy="90" r="160" fill="#dbeafe" opacity="0.45"/>',
        '<circle cx="150" cy="860" r="130" fill="#dcfce7" opacity="0.55"/>',
        '<rect x="48" y="40" width="1504" height="96" rx="28" fill="url(#banner)" filter="url(#shadow)"/>',
        svg_text(88, 86, ['Thiết kế AI Agent tổng thể'], 38, C['white'], '700'),
        svg_text(88, 118, ['Kiến trúc chung cho chatbot ICTU: triển khai từng agent, chuẩn hóa bộ test và đánh giá theo vòng lặp cải tiến.'], 19, '#dbeafe'),
        svg_chip(980, 58, 238, 'Bám theo pipeline hiện tại', '#dbeafe', '#bfdbfe', '#1d4ed8'),
        svg_chip(1232, 58, 278, 'Mở rộng dần bằng agent mới', '#ffedd5', '#fed7aa', '#c2410c'),
        *cards,
        *arrows,
        '</svg>'
    ]
    path = out / 'ai_agent_overview_report.svg'
    path.write_text(''.join(parts), encoding='utf-8')
    return path

def technical_svg():
    W, H = 1900, 1220
    top_cards = [
        svg_card(55, 200, 265, 185, '1. Input + Normalizer', ['services/chat_service.py', '_normalize_input', 'Chuẩn hóa message, session_id, language'], C['blue_fill'], C['sky']),
        svg_card(355, 200, 265, 185, '2. Guardrail + Quick Reply', ['_handle_guardrails', 'moderation_service', 'quick_reply_service'], C['green_fill'], C['emerald']),
        svg_card(655, 200, 265, 185, '3. Router', ['_route_rag', 'services/rag_service.py::route_rag_tool', 'Chọn đúng nhánh tri thức'], C['amber_fill'], C['amber']),
        svg_card(955, 200, 265, 185, '4. Retrieval Layer', ['retrieve_tool_context', 'retrieve_fallback_context', 'student_handbook_rag / school_policy_rag / student_faq_rag / fallback'], C['white'], C['sky']),
        svg_card(1255, 200, 265, 185, '5. Response Composer', ['_generate_response', 'multilingual_service::chat_multilingual', 'gemini_service'], C['orange_fill'], C['orange']),
        svg_card(1555, 200, 290, 185, '6. Finalize + Memory', ['_finalize', 'config.db.save_message', 'SESSION_MEMORY trong vector_store_service'], C['slate_fill'], C['muted']),
    ]
    mid = [
        svg_card(995, 410, 205, 112, 'student_handbook_rag', ['Sổ tay sinh viên'], C['white'], C['sky'], align='center'),
        svg_card(995, 542, 205, 112, 'school_policy_rag', ['Văn bản, quy định'], C['white'], C['emerald'], align='center'),
        svg_card(975, 674, 245, 112, 'student_faq_rag', ['FAQ, thông báo', 'sự kiện'], C['white'], C['amber'], align='center'),
        svg_card(975, 806, 245, 112, 'fallback_rag', ['Tổng hợp khi', 'câu hỏi mơ hồ'], C['white'], C['orange'], align='center'),
    ]
    bottom = [
        svg_card(60, 460, 385, 285, 'Tầng dữ liệu và index', ['clean_data/, data/, vectorstore/', 'knowledge_base_service.py và vector_store_service.py', 'Nguồn: sổ tay, quy định, FAQ, metadata'], C['white'], C['line']),
        svg_card(60, 780, 385, 320, 'Bộ test hiện có', ['evaluation/chatbot_eval_dataset.json', 'Mỗi mẫu có: id, question, expected_tool', 'Một số mẫu có expected_source_contains', 'Dùng để benchmark router và nguồn truy hồi'], C['white'], C['line']),
        svg_card(495, 460, 390, 280, 'Độ đo nên theo dõi', ['Router: accuracy, confusion matrix', 'Retrieval: hit@k, top-1 hit rate, MRR, latency', 'Response: faithfulness, groundedness, completeness', 'Toàn hệ thống: pass rate, thời gian đáp ứng, số nguồn đúng'], C['white'], C['line']),
        svg_card(495, 780, 390, 320, 'Rủi ro kỹ thuật cần canh', ['Router lệch miền tri thức', 'Nguồn đúng nhưng trả lời thiếu', 'Thiếu biến phân biệt như năm học, đợt, khóa', 'Drift chất lượng sau khi nạp tài liệu mới'], C['white'], C['line']),
        svg_card(1290, 470, 555, 250, 'Lộ trình triển khai dần', ['GĐ1: tăng test cho router, retrieval, prompt builder', 'GĐ2: Clarification Agent để hỏi lại đúng 1 câu khi thiếu biến', 'GĐ3: Ingestion Agent để tự nhận PDF, OCR, làm sạch, nạp vector', 'GĐ4: Evaluation Agent chạy benchmark định kỳ'], C['white'], C['orange'], True),
        svg_card(1290, 760, 555, 340, 'Đề xuất cách thử nghiệm từng agent', ['1) Cô lập agent bằng bộ test chuyên biệt', '2) Đo trước và sau mỗi lần thêm agent', '3) Chỉ mở rộng khi agent mới tăng chất lượng hoặc giảm thời gian', '4) Lưu log quyết định của router và nguồn trả lời để debug'], C['white'], C['orange'], True),
    ]
    arrows = [
        svg_arrow(320, 292, 355, 292), svg_arrow(620, 292, 655, 292), svg_arrow(920, 292, 955, 292), svg_arrow(1220, 292, 1255, 292), svg_arrow(1520, 292, 1555, 292),
        svg_polyline([(1087, 385), (1087, 410)]), svg_polyline([(1087, 385), (1087, 542)]), svg_polyline([(1087, 385), (1087, 674)]), svg_polyline([(1087, 385), (1087, 806)]),
        svg_polyline([(445, 520), (520, 520), (520, 330), (655, 330)]), svg_polyline([(445, 920), (520, 920), (520, 330), (655, 330)]),
        svg_polyline([(885, 600), (1087, 600), (1087, 385)]), svg_polyline([(1290, 595), (1220, 595), (1220, 292)], C['orange'], True), svg_polyline([(1290, 930), (1220, 930), (1220, 292)], C['orange'], True),
    ]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">', svg_defs()]
    parts += [
        f'<rect width="{W}" height="{H}" fill="url(#bgMain)"/>',
        '<circle cx="1700" cy="120" r="180" fill="#dbeafe" opacity="0.40"/>',
        '<circle cx="180" cy="1080" r="140" fill="#ffedd5" opacity="0.45"/>',
        '<rect x="52" y="34" width="1796" height="108" rx="30" fill="url(#banner)" filter="url(#shadow)"/>',
        svg_text(92, 84, ['Bản kỹ thuật chi tiết hơn'], 40, C['white'], '700'),
        svg_text(92, 118, ['Mapping kiến trúc agent với code hiện có, tầng dữ liệu, lộ trình mở rộng và bộ đánh giá.'], 20, '#dbeafe'),
        svg_chip(1380, 62, 180, 'Khối hiện tại', '#dbeafe', '#bfdbfe', '#1d4ed8'),
        svg_chip(1580, 62, 210, 'Khối đề xuất', '#ffedd5', '#fed7aa', '#c2410c'),
        *top_cards, *mid, *bottom, *arrows,
        svg_text(70, 1148, ['Gợi ý sử dụng: bản này hợp để đưa vào báo cáo kỹ thuật, slide review kiến trúc hoặc giải thích mapping giữa code và thiết kế agent.'], 18, C['soft']),
        '</svg>'
    ]
    path = out / 'ai_agent_technical_design.svg'
    path.write_text(''.join(parts), encoding='utf-8')
    return path


def shadow_card(base, xy, fill, outline, radius=28):
    shadow = Image.new('RGBA', base.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    x1, y1, x2, y2 = xy
    sd.rounded_rectangle((x1 + 10, y1 + 12, x2 + 10, y2 + 12), radius=radius, fill=(15, 23, 42, 24))
    base.alpha_composite(shadow)
    ImageDraw.Draw(base).rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=3)


def draw_text_lines(draw, x, y, lines, fnt, fill, gap=8):
    cy = y
    for line in lines:
        draw.text((x, cy), line, font=fnt, fill=fill)
        cy += fnt.size + gap


def draw_center_text(draw, box, lines, fnt, fill, gap=6):
    x1, y1, x2, y2 = box
    total_h = len(lines) * fnt.size + max(0, len(lines) - 1) * gap
    cy = y1 + (y2 - y1 - total_h) // 2
    for line in lines:
        w = int(fnt.getlength(line))
        cx = x1 + (x2 - x1 - w) // 2
        draw.text((cx, cy), line, font=fnt, fill=fill)
        cy += fnt.size + gap


def draw_arrow(draw, start, end, fill, width=8):
    draw.line([start, end], fill=fill, width=width)
    sx, sy = start; ex, ey = end
    if abs(ex - sx) >= abs(ey - sy):
        d = 1 if ex >= sx else -1
        pts = [(ex, ey), (ex - 22 * d, ey - 12), (ex - 22 * d, ey + 12)]
    else:
        d = 1 if ey >= sy else -1
        pts = [(ex, ey), (ex - 12, ey - 22 * d), (ex + 12, ey - 22 * d)]
    draw.polygon(pts, fill=fill)

def slide_png():
    W, H = 1920, 1080
    img = Image.new('RGBA', (W, H), rgba('#f7fbff'))
    draw = ImageDraw.Draw(img)
    for y in range(H):
        blend = y / H
        r = int(247 * (1 - blend) + 240 * blend)
        g = int(251 * (1 - blend) + 248 * blend)
        b = int(255 * (1 - blend) + 255 * blend)
        draw.line((0, y, W, y), fill=(r, g, b, 255))
    draw.ellipse((1450, -60, 2020, 510), fill=rgba('#dbeafe', 180))
    draw.ellipse((-120, 760, 430, 1310), fill=rgba('#dcfce7', 180))
    draw.rounded_rectangle((72, 56, 1848, 188), radius=42, fill=rgba(C['navy']), outline=rgba('#1d4ed8'), width=3)

    title_font = font(44, True)
    subtitle_font = font(21)
    chip_font = font(18, True)
    stage_font = font(24, True)
    body_font = font(22)
    card_title = font(25, True)
    card_body = font(18)
    panel_title = font(28, True)
    panel_body = font(21)
    small = font(16)

    draw.text((118, 90), 'Thiết kế AI Agent tổng thể cho Chatbot ICTU', font=title_font, fill=rgba(C['white']))
    draw.text((118, 145), 'Kiến trúc chung, lộ trình triển khai từng agent, bộ dữ liệu test và các độ đo đánh giá cốt lõi.', font=subtitle_font, fill=rgba('#dbeafe'))
    draw.rounded_rectangle((1470, 92, 1760, 138), radius=23, fill=rgba('#dbeafe'), outline=rgba('#bfdbfe'), width=2)
    draw.rounded_rectangle((1470, 146, 1808, 192), radius=23, fill=rgba('#ffedd5'), outline=rgba('#fed7aa'), width=2)
    draw.text((1492, 105), 'Theo pipeline hiện tại', font=chip_font, fill=rgba('#1d4ed8'))
    draw.text((1492, 159), 'Mở rộng bằng agent mới', font=chip_font, fill=rgba('#c2410c'))

    flow = [
        (110, 280, 330, 418, '1. Input + Normalizer', ['Chuẩn hóa câu hỏi', 'session, ngôn ngữ'], C['blue_fill'], C['sky']),
        (395, 280, 615, 418, '2. Guardrail', ['Lọc nội dung xấu', 'quick reply'], C['green_fill'], C['emerald']),
        (680, 280, 900, 418, '3. Router', ['Chọn đúng tool', 'RAG'], C['amber_fill'], C['amber']),
        (965, 280, 1185, 418, '4. Retrieval', ['Handbook / Policy', 'FAQ / Fallback'], C['white'], C['sky']),
        (1250, 280, 1470, 418, '5. Response', ['Tổng hợp ngữ cảnh', 'sinh phản hồi'], C['orange_fill'], C['orange']),
    ]
    for x1, y1, x2, y2, title, lines, fill, stroke in flow:
        shadow_card(img, (x1, y1, x2, y2), rgba(fill), rgba(stroke))
        draw_center_text(draw, (x1 + 18, y1 + 18, x2 - 18, y1 + 70), wrap_pixels(title, card_title, x2 - x1 - 36), card_title, rgba(C['navy']))
        draw_center_text(draw, (x1 + 18, y1 + 86, x2 - 18, y2 - 20), lines, card_body, rgba(C['muted']), 4)
    for i in range(len(flow) - 1):
        draw_arrow(draw, (flow[i][2], 349), (flow[i + 1][0], 349), rgba('#2563eb'))

    shadow_card(img, (1525, 260, 1835, 682), rgba(C['white']), rgba(C['orange']))
    draw.text((1560, 294), 'Triển khai 4 giai đoạn', font=stage_font, fill=rgba(C['navy']))
    stages = [
        ('GĐ1', 'Củng cố pipeline hiện tại và tăng test.'),
        ('GĐ2', 'Thêm Clarification Agent để hỏi lại đúng 1 câu.'),
        ('GĐ3', 'Thêm Ingestion Agent cho PDF, OCR, index.'),
        ('GĐ4', 'Thêm Evaluation Agent để benchmark định kỳ.'),
    ]
    fills = [rgba('#dbeafe'), rgba('#dcfce7'), rgba('#fef3c7'), rgba('#ffedd5')]
    txt = [rgba('#1d4ed8'), rgba('#047857'), rgba('#b45309'), rgba('#c2410c')]
    cy = 360
    for i, (tag, text) in enumerate(stages):
        draw.ellipse((1560, cy - 6, 1614, cy + 48), fill=fills[i], outline=rgba(C['line']), width=2)
        lw = int(chip_font.getlength(tag))
        draw.text((1587 - lw // 2, cy + 7), tag, font=chip_font, fill=txt[i])
        draw_text_lines(draw, 1640, cy, wrap_pixels(text, body_font, 190), body_font, rgba(C['muted']), 6)
        cy += 88

    panels = [
        (110, 500, 650, 900, 'Bộ dữ liệu test', ['- Dataset chuẩn theo nhóm nghiệp vụ', '- Có expected_tool và expected_source_contains', '- Dùng để benchmark router, retrieval, response'], C['white'], C['line']),
        (690, 500, 1230, 900, 'Độ đo đánh giá cốt lõi', ['- Router accuracy, confusion matrix', '- hit@k, top-1 hit rate, MRR, latency', '- faithfulness, groundedness, pass rate'], C['white'], C['line']),
        (1270, 730, 1835, 990, 'Thông điệp chính', ['Thiết kế nên bắt đầu từ pipeline hiện có,', 'triển khai thử từng agent độc lập,', 'đo chất lượng bằng bộ test chuẩn,', 'sau đó mới mở rộng toàn hệ thống.'], C['white'], C['orange']),
    ]
    for x1, y1, x2, y2, title, lines, fill, stroke in panels:
        shadow_card(img, (x1, y1, x2, y2), rgba(fill), rgba(stroke))
        draw.text((x1 + 30, y1 + 28), title, font=panel_title, fill=rgba(C['navy']))
        ty = y1 + 82
        for line in lines:
            wrapped = wrap_pixels(line, panel_body, x2 - x1 - 60)
            draw_text_lines(draw, x1 + 30, ty, wrapped, panel_body, rgba(C['muted']), 6)
            ty += len(wrapped) * (panel_body.size + 6) + 14

    now_text = datetime.now(timezone(timedelta(hours=7))).strftime('%d/%m/%Y')
    draw.text((120, 1010), f'Tài liệu trực quan sinh tự động từ kiến trúc hiện có trong repo | Cập nhật: {now_text}', font=small, fill=rgba(C['soft']))
    path = out / 'ai_agent_presentation_slide.png'
    img.convert('RGB').save(path)
    return path

def pptx_from_png(image_path):
    pptx = out / 'ai_agent_presentation_slide.pptx'
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    image_name = image_path.name
    slide_cx = 12192000
    slide_cy = 6858000
    files = {
        '[Content_Types].xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n  <Default Extension="xml" ContentType="application/xml"/>\n  <Default Extension="png" ContentType="image/png"/>\n  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>\n  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>\n  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>\n  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>\n  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>\n  <Override PartName="/ppt/presProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"/>\n  <Override PartName="/ppt/viewProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"/>\n  <Override PartName="/ppt/tableStyles.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"/>\n  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>\n  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>\n</Types>''',
        '_rels/.rels': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>\n  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>\n  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>\n</Relationships>''',
        'docProps/app.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">\n  <Application>Codex</Application><PresentationFormat>Widescreen</PresentationFormat><Slides>1</Slides><Notes>0</Notes><HiddenSlides>0</HiddenSlides><MMClips>0</MMClips><ScaleCrop>false</ScaleCrop><HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Slides</vt:lpstr></vt:variant><vt:variant><vt:i4>1</vt:i4></vt:variant></vt:vector></HeadingPairs><TitlesOfParts><vt:vector size="1" baseType="lpstr"><vt:lpstr>AI Agent Presentation Slide</vt:lpstr></vt:vector></TitlesOfParts><Company>OpenAI Codex</Company><LinksUpToDate>false</LinksUpToDate><SharedDoc>false</SharedDoc><HyperlinksChanged>false</HyperlinksChanged><AppVersion>1.0</AppVersion>\n</Properties>''',
        'docProps/core.xml': f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>AI Agent Presentation Slide</dc:title><dc:subject>AI Agent architecture</dc:subject><dc:creator>Codex</dc:creator><cp:lastModifiedBy>Codex</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>''',
        'ppt/presentation.xml': f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" saveSubsetFonts="1" autoCompressPictures="0"><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst><p:sldId id="256" r:id="rId5"/></p:sldIdLst><p:sldSz cx="{slide_cx}" cy="{slide_cy}"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>''',
        'ppt/_rels/presentation.xml.rels': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps" Target="presProps.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps" Target="viewProps.xml"/><Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles" Target="tableStyles.xml"/><Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/></Relationships>''',
        'ppt/presProps.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<p:presentationPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>''',
        'ppt/viewProps.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<p:viewPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:normalViewPr><p:restoredLeft sz="15620"/><p:restoredTop sz="94660"/></p:normalViewPr><p:slideViewPr scale="100000"/><p:notesTextViewPr scale="100000"/><p:gridSpacing cx="780288" cy="780288"/></p:viewPr>''',
        'ppt/tableStyles.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>''',
        'ppt/slideMasters/slideMaster1.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld name="Blank Master"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld><p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/><p:sldLayoutIdLst><p:sldLayoutId id="1" r:id="rId1"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>''',
        'ppt/slideMasters/_rels/slideMaster1.xml.rels': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/></Relationships>''',
        'ppt/slideLayouts/slideLayout1.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1"><p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>''',
        'ppt/slideLayouts/_rels/slideLayout1.xml.rels': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>''',
        'ppt/theme/theme1.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Office Theme"><a:themeElements><a:clrScheme name="Office"><a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1><a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="1F2937"/></a:dk2><a:lt2><a:srgbClr val="F8FAFC"/></a:lt2><a:accent1><a:srgbClr val="2563EB"/></a:accent1><a:accent2><a:srgbClr val="10B981"/></a:accent2><a:accent3><a:srgbClr val="F59E0B"/></a:accent3><a:accent4><a:srgbClr val="F97316"/></a:accent4><a:accent5><a:srgbClr val="0EA5E9"/></a:accent5><a:accent6><a:srgbClr val="64748B"/></a:accent6><a:hlink><a:srgbClr val="2563EB"/></a:hlink><a:folHlink><a:srgbClr val="7C3AED"/></a:folHlink></a:clrScheme><a:fontScheme name="Office"><a:majorFont><a:latin typeface="Segoe UI"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont><a:minorFont><a:latin typeface="Segoe UI"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme><a:fmtScheme name="Office"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst><a:lnStyleLst><a:ln w="9525" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst></a:fmtScheme></a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>''',
        'ppt/slides/slide1.xml': f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld name="AI Agent Design"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr><p:pic><p:nvPicPr><p:cNvPr id="2" name="{escape(image_name)}"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rId2"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{slide_cx}" cy="{slide_cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>''',
        'ppt/slides/_rels/slide1.xml.rels': f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{escape(image_name)}"/></Relationships>''',
    }
    with ZipFile(pptx, 'w', ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
        zf.write(image_path, f'ppt/media/{image_name}')
    return pptx


overview = overview_svg()
tech = technical_svg()
png = slide_png()
pptx = pptx_from_png(png)
readme = out / 'README.md'
readme.write_text('\n'.join([
    '# AI Agent diagram outputs', '',
    '- ai_agent_overview_report.svg: sơ đồ tổng quan để chèn báo cáo.',
    '- ai_agent_technical_design.svg: bản kỹ thuật chi tiết hơn.',
    '- ai_agent_presentation_slide.png: slide PNG tiếng Việt.',
    '- ai_agent_presentation_slide.pptx: PowerPoint 1 slide, tỷ lệ 16:9.'
]), encoding='utf-8')

for item in [overview, tech, png, pptx, readme]:
    print(item)
