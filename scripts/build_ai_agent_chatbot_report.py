from __future__ import annotations

import json
import re
import sqlite3
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports"
GENERATED_DIR = REPORT_DIR / "generated"
DIAGRAM_DIR = GENERATED_DIR / "ai_agent_diagrams"

REPORT_MD = REPORT_DIR / "bao_cao_ai_agent_chatbot.md"
REPORT_DOCX = REPORT_DIR / "bao_cao_ai_agent_chatbot.docx"
REPORT_JSON = GENERATED_DIR / "ai_agent_chatbot_report_payload.json"

QA_ROOT = ROOT / "data" / "qa_generated_fixed"
EVAL_DATASET = ROOT / "evaluation" / "chatbot_eval_dataset.json"
EVAL_RESULTS = GENERATED_DIR / "eval_results.json"
UNITTEST_SUMMARY = GENERATED_DIR / "unittest_summary.json"
VECTOR_SQLITE = ROOT / "vectorstore" / "chroma.sqlite3"

DIAGRAMS = [
    DIAGRAM_DIR / "rag_agent_ecosystem_style.png",
    DIAGRAM_DIR / "ai_agent_presentation_slide.png",
    DIAGRAM_DIR / "ai_agent_reference_style.png",
]

EMU_PER_INCH = 914400


def safe_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def iter_corpus_files() -> list[Path]:
    if not QA_ROOT.exists():
        return []
    return sorted(
        path
        for path in QA_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt"}
    )


def detect_tool(path: Path) -> str:
    normalized = path.as_posix().casefold()
    if "sổ tay sinh viên" in normalized or "so tay sinh vien" in normalized:
        return "student_handbook_rag"
    if any(token in normalized for token in ("faq", "congvanvieclam", "congvanxettn")):
        return "student_faq_rag"
    return "school_policy_rag"


def analyze_corpus() -> dict[str, Any]:
    files = iter_corpus_files()
    tool_counts: Counter[str] = Counter()
    qa_pairs = 0
    question_files = 0
    handbook_question_files = 0
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        tool_counts[detect_tool(path)] += 1
        if path.name.endswith(".questions.md"):
            question_files += 1
            if "Sổ tay sinh viên" in path.as_posix() or "SO TAY SINH VIEN" in path.as_posix():
                handbook_question_files += 1
        qa_pairs += len(re.findall(r"^\*\*Q:\*\*", text, flags=re.MULTILINE))
        qa_pairs += len(re.findall(r"^##\s+Câu hỏi\s+\d+", text, flags=re.MULTILINE))
    return {
        "total_files": len(files),
        "question_files": question_files,
        "handbook_question_files": handbook_question_files,
        "qa_pairs": qa_pairs,
        "tool_distribution": dict(sorted(tool_counts.items())),
    }


def vector_summary() -> dict[str, Any]:
    if not VECTOR_SQLITE.exists():
        return {"sources": 0, "embeddings": 0, "question_sources": 0, "handbook_sources": 0}
    con = sqlite3.connect(VECTOR_SQLITE)
    try:
        cur = con.cursor()
        embeddings = cur.execute("select count(*) from embeddings").fetchone()[0]
        rows = cur.execute("select string_value from embedding_metadata where key=?", ("source",)).fetchall()
    finally:
        con.close()
    counts = Counter(value for (value,) in rows if value)
    return {
        "sources": len(counts),
        "embeddings": embeddings,
        "question_sources": sum(1 for source in counts if str(source).endswith(".questions.md")),
        "handbook_sources": sum(1 for source in counts if "Sổ tay sinh viên" in str(source) or "SO TAY SINH VIEN" in str(source)),
    }


def eval_dataset_summary() -> dict[str, Any]:
    data = load_json(EVAL_DATASET, [])
    if not isinstance(data, list):
        return {"total_cases": 0, "labeled_source_cases": 0, "expected_tool_distribution": {}}
    tool_counts = Counter(item.get("expected_tool", "unknown") for item in data if isinstance(item, dict))
    return {
        "total_cases": len(data),
        "labeled_source_cases": sum(1 for item in data if isinstance(item, dict) and item.get("expected_source_contains")),
        "expected_tool_distribution": dict(sorted(tool_counts.items())),
    }


def eval_result_summary() -> dict[str, Any]:
    report = load_json(EVAL_RESULTS, {})
    return {
        "total_cases": report.get("total_cases", 0),
        "route_accuracy": report.get("route_accuracy", 0),
        "source_hit_rate": report.get("source_hit_rate", 0),
        "source_top1_hit_rate": report.get("source_top1_hit_rate", 0),
        "source_mrr": report.get("source_mrr", 0),
        "avg_latency_ms": report.get("avg_latency_ms", 0),
        "avg_chunks_used": report.get("avg_chunks_used", 0),
        "failing_cases": len(report.get("failing_cases", [])),
    }


def unittest_summary() -> dict[str, Any]:
    report = load_json(UNITTEST_SUMMARY, {})
    return {
        "status": report.get("status", "unknown"),
        "tests_ran": report.get("tests_ran", 0),
        "duration_seconds": report.get("duration_seconds", 0),
    }


def pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "0.00%"


def build_payload() -> dict[str, Any]:
    missing = [str(path) for path in DIAGRAMS if not path.exists()]
    if missing:
        raise FileNotFoundError("Chưa có sơ đồ PNG cần nhúng: " + ", ".join(missing))
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "prompt": [
            "Vẽ bản thiết kế AI Agent chung hệ thống, triển khai thử nghiệm dần từng agent.",
            "Làm bộ dữ liệu test và độ đo đánh giá.",
            "Bản thiết kế chatbot tổng quát.",
            "Framework hỗ trợ cho từng bước xử lý chatbot.",
            "Đưa nội dung và sơ đồ vào file DOCX để báo cáo.",
        ],
        "corpus": analyze_corpus(),
        "vector": vector_summary(),
        "eval_dataset": eval_dataset_summary(),
        "eval_results": eval_result_summary(),
        "unittest": unittest_summary(),
        "diagrams": [path.relative_to(ROOT).as_posix() for path in DIAGRAMS],
    }


def build_markdown(payload: dict[str, Any]) -> str:
    corpus = payload["corpus"]
    vector = payload["vector"]
    eval_data = payload["eval_dataset"]
    eval_result = payload["eval_results"]
    tests = payload["unittest"]
    lines = [
        "# Báo cáo thiết kế AI Agent và chatbot RAG ICTU",
        "",
        f"- Ngày tổng hợp: {payload['generated_at']}",
        "- Phạm vi: thiết kế AI Agent, thiết kế chatbot tổng quát, framework xử lý, bộ test và độ đo đánh giá.",
        "",
        "## 1. Nhắc lại prompt/yêu cầu trước khi làm",
        "",
    ]
    lines += [f"- {item}" for item in payload["prompt"]]
    lines += [
        "",
        "## 2. Kết luận nhanh",
        "",
        "- Hệ thống hiện đã có nền tảng chatbot RAG theo pipeline agent: normalize, guardrail, router, retrieval, response composer và memory/logging.",
        "- Báo cáo này đóng gói lại các phần đã có, bổ sung diễn giải và nhúng trực tiếp sơ đồ vào file DOCX.",
        f"- Corpus hiện có {corpus['total_files']} file trong data/qa_generated_fixed; có {corpus['question_files']} file .questions.md và {corpus['handbook_question_files']} file câu hỏi thuộc Sổ tay sinh viên.",
        f"- Vector database hiện có {vector['sources']} nguồn tài liệu, {vector['embeddings']} embeddings/chunks và {vector['question_sources']} source .questions.md.",
        f"- Bộ test hiện có {eval_data['total_cases']} ca, trong đó {eval_data['labeled_source_cases']} ca có nhãn nguồn để đo retrieval.",
        "",
        "## 3. Bản thiết kế AI Agent chung hệ thống",
        "",
        f"![Sơ đồ AI Agent + RAG]({payload['diagrams'][0]})",
        "",
        "- AI Agent là bộ điều phối trung tâm giữa người dùng, LLM, RAG, web/API và các thao tác quản trị tri thức.",
        "- Bên trong RAG: query được tạo embedding, truy vấn vector database, lấy candidates, ghép prompt có context và đưa sang LLM sinh trả lời.",
        "- Các nhánh ngoài RAG gồm Web UI/Partner API, hệ thống trường/external API và knowledge actions như upload, approve, index.",
        "",
        "### Lộ trình triển khai thử nghiệm dần từng agent",
        "",
        "- Giai đoạn 1: củng cố pipeline hiện tại và tăng test cho router, retrieval, prompt builder, upload/indexing.",
        "- Giai đoạn 2: thêm Clarification Agent để hỏi lại khi thiếu năm học, học kỳ, khóa, hệ đào tạo hoặc đợt xét.",
        "- Giai đoạn 3: thêm Ingestion Agent để nhận PDF/tài liệu mới, OCR, làm sạch, phân loại tool và nạp vector store.",
        "- Giai đoạn 4: thêm Evaluation Agent để chạy benchmark định kỳ sau mỗi lần cập nhật dữ liệu, prompt hoặc model.",
        "",
        "## 4. Bản thiết kế chatbot tổng quát",
        "",
        f"![Sơ đồ thiết kế chatbot tổng quát]({payload['diagrams'][1]})",
        "",
        "- Người dùng gửi câu hỏi qua Web/API.",
        "- Input Normalizer chuẩn hóa message, session_id, ngôn ngữ và model được chọn.",
        "- Guardrail kiểm tra nội dung không phù hợp và trả lời nhanh các lời chào/input đơn giản.",
        "- Router chọn tool tri thức: student_handbook_rag, school_policy_rag, student_faq_rag hoặc fallback_rag.",
        "- Retrieval lấy nguồn/chunk liên quan từ corpus, upload hoặc vector store.",
        "- Response Composer ghép ngữ cảnh vào prompt và gọi LLM để sinh câu trả lời cuối.",
        "- Finalize lưu response, nguồn truy hồi, session memory và log phục vụ đánh giá sau này.",
        "",
        "## 5. Framework hỗ trợ từng bước xử lý chatbot",
        "",
        f"![Framework AI Agent]({payload['diagrams'][2]})",
        "",
        "- Framework chia hệ thống thành các khối nhỏ: Input, Guardrail, Router, Retrieval, Response, Memory/Logging, Evaluation.",
        "- Mỗi khối có đầu vào/đầu ra rõ ràng nên có thể kiểm thử độc lập trước khi đưa vào pipeline chính.",
        "- Khi thêm agent mới, cần chạy lại benchmark để tránh giảm chất lượng router, retrieval hoặc câu trả lời.",
        "",
        "## 6. Bộ dữ liệu test",
        "",
        "- File test chính: evaluation/chatbot_eval_dataset.json.",
        f"- Số ca kiểm thử: {eval_data['total_cases']}.",
        f"- Số ca có nhãn nguồn: {eval_data['labeled_source_cases']}.",
        "- Mỗi ca gồm id, question, expected_tool và tùy ca có expected_source_contains.",
        "- Bộ test bao phủ handbook, policy, FAQ/thông báo và câu hỏi mơ hồ.",
        "",
        "Phân bố expected_tool:",
    ]
    for tool, count in eval_data["expected_tool_distribution"].items():
        lines.append(f"- {tool}: {count} ca.")
    lines += [
        "",
        "## 7. Độ đo đánh giá",
        "",
        "- Router accuracy: tỷ lệ chọn đúng nhóm tri thức/tool.",
        "- Confusion matrix: xác định router hay nhầm giữa handbook, policy, FAQ hay fallback.",
        "- Retrieval hit@k: nguồn đúng có nằm trong top-k kết quả hay không.",
        "- Top-1 hit rate: nguồn đúng có đứng đầu danh sách hay không.",
        "- MRR: đo thứ hạng trung bình có trọng số của nguồn đúng.",
        "- Latency: thời gian phản hồi cho từng truy vấn.",
        "- Chunks used: số đoạn tri thức đã dùng để sinh câu trả lời.",
        "- Faithfulness/groundedness: câu trả lời có bám nguồn hay không.",
        "- Completeness/relevance: câu trả lời có đầy đủ và đúng trọng tâm không.",
        "- Regression pass rate: tỷ lệ test tự động vẫn pass sau khi đổi dữ liệu, prompt hoặc model.",
        "",
        "## 8. Kết quả đo hiện có",
        "",
        f"- Route accuracy: {pct(eval_result['route_accuracy'])}.",
        f"- Source hit rate: {pct(eval_result['source_hit_rate'])}.",
        f"- Source top-1 hit rate: {pct(eval_result['source_top1_hit_rate'])}.",
        f"- Source MRR: {eval_result['source_mrr']}.",
        f"- Độ trễ trung bình: {eval_result['avg_latency_ms']} ms.",
        f"- Số chunk trung bình mỗi truy vấn: {eval_result['avg_chunks_used']}.",
        f"- Số ca benchmark lỗi: {eval_result['failing_cases']}.",
        f"- Unit test: {tests['tests_ran']} test, trạng thái {tests['status']}, thời gian {tests['duration_seconds']} giây.",
        "",
        "## 9. Minh chứng trong code hiện tại",
        "",
        "- services/chat_service.py: normalize, persist_user, guardrails, route_rag, retrieve theo tool, generate_response, finalize.",
        "- services/rag_service.py: route_rag_tool, retrieve_tool_context, retrieve_fallback_context, retrieve_general_context.",
        "- services/vector_store_service.py: ChromaDB, embedding, smart_chunk, BM25, hybrid search, session memory.",
        "- evaluation/chatbot_eval_dataset.json: bộ câu hỏi benchmark.",
        "- reports/generated/eval_results.json: kết quả đo router/retrieval.",
        "- tests/: test hồi quy cho fallback model, prompt builder, upload flow và vector manager payload.",
        "",
        "## 10. Tệp bàn giao",
        "",
        "- reports/bao_cao_ai_agent_chatbot.docx",
        "- reports/bao_cao_ai_agent_chatbot.md",
        "- reports/generated/ai_agent_chatbot_report_payload.json",
    ]
    return "\n".join(lines) + "\n"


def clean_xml(text: str) -> str:
    return "".join(ch for ch in text if ch in "\t\n\r" or ord(ch) >= 32)


def para(text: str = "", style: str | None = None) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    if not text:
        return f"<w:p>{ppr}</w:p>"
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(clean_xml(text))}</w:t></w:r></w:p>'


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


def build_docx(markdown: str, output: Path) -> None:
    rels: dict[str, tuple[str, str, int, int]] = {}
    rel_xml: list[str] = []
    media: list[tuple[Path, str]] = []
    for index, image_path in enumerate(DIAGRAMS, start=1):
        rel_id = f"rId{index}"
        media_name = f"image{index}.png"
        with Image.open(image_path) as img:
            w, h = img.size
        cx = int(6.85 * EMU_PER_INCH)
        cy = int(cx * h / w)
        rel_key = image_path.relative_to(ROOT).as_posix()
        rels[rel_key] = (rel_id, media_name, cx, cy)
        rel_xml.append(f'<Relationship Id="{rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{media_name}"/>')
        media.append((image_path, media_name))

    body: list[str] = []
    pic_id = 1
    for raw in markdown.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        match = re.match(r"!\[(.*?)\]\((.*?)\)", stripped)
        if match:
            rel_id, name, cx, cy = rels[match.group(2)]
            body.append(image_xml(rel_id, pic_id, name, cx, cy))
            pic_id += 1
        elif stripped.startswith("# "):
            body.append(para(stripped[2:], "Title"))
        elif stripped.startswith("## "):
            body.append(para(stripped[3:], "Heading1"))
        elif stripped.startswith("### "):
            body.append(para(stripped[4:], "Heading2"))
        elif stripped.startswith("- "):
            body.append(para(stripped, "ListParagraph"))
        else:
            body.append(para(line))
    body.append('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="900" w:right="900" w:bottom="900" w:left="900" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>')

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    document = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><w:body>{''.join(body)}</w:body></w:document>"""
    styles = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr><w:rPr><w:rFonts w:ascii="Segoe UI" w:hAnsi="Segoe UI"/><w:sz w:val="22"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:rPr><w:rFonts w:ascii="Segoe UI" w:hAnsi="Segoe UI"/><w:b/><w:sz w:val="34"/><w:color w:val="1F2A63"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="Heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="260" w:after="140"/></w:pPr><w:rPr><w:rFonts w:ascii="Segoe UI" w:hAnsi="Segoe UI"/><w:b/><w:sz w:val="28"/><w:color w:val="1F2A63"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="Heading 2"/><w:basedOn w:val="Normal"/><w:rPr><w:rFonts w:ascii="Segoe UI" w:hAnsi="Segoe UI"/><w:b/><w:sz w:val="24"/><w:color w:val="46536C"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="360" w:hanging="180"/><w:spacing w:after="90"/></w:pPr></w:style>
</w:styles>"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>"""
    doc_rels = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{''.join(rel_xml)}</Relationships>"""
    app = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Codex</Application></Properties>"""
    core = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>Báo cáo thiết kế AI Agent và chatbot RAG ICTU</dc:title><dc:creator>Codex</dc:creator><cp:lastModifiedBy>Codex</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types)
        docx.writestr("_rels/.rels", root_rels)
        docx.writestr("docProps/app.xml", app)
        docx.writestr("docProps/core.xml", core)
        docx.writestr("word/document.xml", document)
        docx.writestr("word/styles.xml", styles)
        docx.writestr("word/_rels/document.xml.rels", doc_rels)
        for image_path, media_name in media:
            docx.write(image_path, f"word/media/{media_name}")


def main() -> None:
    safe_stdout()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_payload()
    markdown = build_markdown(payload)
    REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_MD.write_text(markdown, encoding="utf-8")
    build_docx(markdown, REPORT_DOCX)
    print(json.dumps({"status": "ok", "report_docx": str(REPORT_DOCX), "report_md": str(REPORT_MD), "payload_json": str(REPORT_JSON)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
