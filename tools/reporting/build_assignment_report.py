from __future__ import annotations

import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image


def _find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "main.py").exists() and (parent / "services").is_dir():
            return parent
    return Path(__file__).resolve().parents[2]


ROOT = _find_repo_root()
REPORTING_DIR = Path(__file__).resolve().parent
for candidate in [ROOT, REPORTING_DIR]:
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from generate_assignment_chatbot_diagram import generate_diagram_assets  # noqa: E402
from services.document_service import get_vector_manager_payload  # noqa: E402


REPORT_DIR = ROOT / "reports"
GENERATED_DIR = REPORT_DIR / "generated"
REPORT_MD_PATH = REPORT_DIR / "bao_cao_nhiem_vu_chatbot.md"
REPORT_DOCX_PATH = REPORT_DIR / "bao_cao_nhiem_vu_chatbot.docx"
UNITTEST_JSON_PATH = GENERATED_DIR / "unittest_summary.json"

EMU_PER_INCH = 914400


def _run_subprocess(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _run_analysis() -> dict:
    result = _run_subprocess([sys.executable, str(ROOT / "scripts" / "analyze_dataset.py")])
    if result.returncode != 0:
        raise RuntimeError(f"Phân tích dữ liệu thất bại:\n{result.stdout}\n{result.stderr}")
    return json.loads((GENERATED_DIR / "dataset_analysis.json").read_text(encoding="utf-8"))


def _run_evaluation() -> dict:
    result = _run_subprocess([sys.executable, str(ROOT / "scripts" / "evaluate_chatbot.py")])
    if result.returncode != 0:
        raise RuntimeError(f"Benchmark chatbot thất bại:\n{result.stdout}\n{result.stderr}")
    return json.loads((GENERATED_DIR / "eval_results.json").read_text(encoding="utf-8"))


def _run_unittest() -> dict:
    result = _run_subprocess([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    combined_output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    ran_match = re.search(r"Ran\s+(\d+)\s+tests?\s+in\s+([0-9.]+)s", combined_output)
    tests_ran = int(ran_match.group(1)) if ran_match else 0
    duration_seconds = float(ran_match.group(2)) if ran_match else 0.0
    warnings: list[str] = []

    if "FutureWarning" in combined_output and "google.generativeai" in combined_output:
        warnings.append("Thư viện google.generativeai đang ở trạng thái deprecated.")

    summary = {
        "status": "passed" if result.returncode == 0 else "failed",
        "tests_ran": tests_ran,
        "duration_seconds": duration_seconds,
        "returncode": result.returncode,
        "warnings": warnings,
        "output_excerpt": combined_output[-4000:],
        "generated_at": datetime.now().astimezone().isoformat(),
    }
    UNITTEST_JSON_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _format_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _format_date(value: str) -> str:
    dt = datetime.fromisoformat(value)
    return dt.strftime("%d/%m/%Y %H:%M")


def _join_distribution(distribution: dict) -> str:
    if not distribution:
        return "không có"
    return ", ".join(f"{key}={value}" for key, value in distribution.items())


def _invalid_xml_chars_removed(text: str) -> str:
    return "".join(ch for ch in text if ch == "\t" or ch == "\n" or ch == "\r" or ord(ch) >= 32)


def _paragraph_xml(text: str, style: str | None = None) -> str:
    safe_text = escape(_invalid_xml_chars_removed(text))
    style_xml = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    if not safe_text:
        return f"<w:p>{style_xml}</w:p>"
    return (
        "<w:p>"
        f"{style_xml}"
        "<w:r>"
        f'<w:t xml:space="preserve">{safe_text}</w:t>'
        "</w:r>"
        "</w:p>"
    )


def _image_xml(rel_id: str, pic_id: int, name: str, cx: int, cy: int) -> str:
    safe_name = escape(name)
    return f"""
<w:p>
  <w:pPr><w:jc w:val="center"/></w:pPr>
  <w:r>
    <w:drawing>
      <wp:inline distT="0" distB="0" distL="0" distR="0">
        <wp:extent cx="{cx}" cy="{cy}"/>
        <wp:docPr id="{pic_id}" name="{safe_name}"/>
        <a:graphic>
          <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
            <pic:pic>
              <pic:nvPicPr>
                <pic:cNvPr id="{pic_id}" name="{safe_name}"/>
                <pic:cNvPicPr/>
              </pic:nvPicPr>
              <pic:blipFill>
                <a:blip r:embed="{rel_id}"/>
                <a:stretch><a:fillRect/></a:stretch>
              </pic:blipFill>
              <pic:spPr>
                <a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>
                <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
              </pic:spPr>
            </pic:pic>
          </a:graphicData>
        </a:graphic>
      </wp:inline>
    </w:drawing>
  </w:r>
</w:p>
"""


def _parse_markdown_images(markdown_text: str) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for raw_line in markdown_text.splitlines():
        stripped = raw_line.strip()
        match = re.match(r"!\[(.*?)\]\((.*?)\)", stripped)
        if not match:
            continue
        ref = match.group(2).strip()
        if ref not in seen:
            refs.append(ref)
            seen.add(ref)
    return refs


def _resolve_markdown_image_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return ROOT / path


def _build_docx(markdown_text: str, output_path: Path) -> None:
    image_refs = _parse_markdown_images(markdown_text)
    rel_map: dict[str, tuple[str, str, int, int, Path]] = {}
    rel_xml: list[str] = []
    media: list[tuple[Path, str]] = []

    for index, ref in enumerate(image_refs, start=1):
        image_path = _resolve_markdown_image_path(ref)
        if not image_path.exists():
            raise FileNotFoundError(f"Thiếu ảnh để nhúng DOCX: {image_path}")

        with Image.open(image_path) as img:
            width, height = img.size

        cx = int(6.75 * EMU_PER_INCH)
        cy = int(cx * height / width)
        max_cy = int(7.7 * EMU_PER_INCH)
        if cy > max_cy:
            cy = max_cy
            cx = int(cy * width / height)

        rel_id = f"rId{index}"
        media_name = f"image{index}{image_path.suffix.lower()}"
        rel_map[ref] = (rel_id, media_name, cx, cy, image_path)
        rel_xml.append(
            f'<Relationship Id="{rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{media_name}"/>'
        )
        media.append((image_path, media_name))

    body_parts: list[str] = []
    pic_id = 1
    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        image_match = re.match(r"!\[(.*?)\]\((.*?)\)", stripped)
        if image_match:
            rel_id, name, cx, cy, _ = rel_map[image_match.group(2)]
            body_parts.append(_image_xml(rel_id, pic_id, image_match.group(1) or name, cx, cy))
            pic_id += 1
        elif stripped.startswith("# "):
            body_parts.append(_paragraph_xml(stripped[2:], "Title"))
        elif stripped.startswith("## "):
            body_parts.append(_paragraph_xml(stripped[3:], "Heading1"))
        elif stripped.startswith("### "):
            body_parts.append(_paragraph_xml(stripped[4:], "Heading2"))
        elif stripped.startswith("- "):
            body_parts.append(_paragraph_xml(stripped, "ListParagraph"))
        elif re.match(r"\d+\.\s", stripped):
            body_parts.append(_paragraph_xml(stripped, "ListParagraph"))
        else:
            body_parts.append(_paragraph_xml(line))

    body_parts.append(
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="900" w:right="900" w:bottom="900" w:left="900" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
    )

    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
            xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
            xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
  <w:body>{''.join(body_parts)}</w:body>
</w:document>
"""
    styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Segoe UI" w:hAnsi="Segoe UI"/><w:sz w:val="22"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:basedOn w:val="Normal"/>
    <w:rPr><w:rFonts w:ascii="Segoe UI" w:hAnsi="Segoe UI"/><w:b/><w:sz w:val="34"/><w:color w:val="102542"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="Heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:before="280" w:after="140"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Segoe UI" w:hAnsi="Segoe UI"/><w:b/><w:sz w:val="28"/><w:color w:val="163963"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="Heading 2"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:before="180" w:after="100"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Segoe UI" w:hAnsi="Segoe UI"/><w:b/><w:sz w:val="24"/><w:color w:val="334E68"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="ListParagraph">
    <w:name w:val="List Paragraph"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:ind w:left="360" w:hanging="180"/><w:spacing w:after="90"/></w:pPr>
  </w:style>
</w:styles>
"""
    content_types_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""
    root_rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""
    document_rels_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  {''.join(rel_xml)}
</Relationships>
"""
    app_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
            xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Codex</Application>
</Properties>
"""
    core_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/"
                   xmlns:dcterms="http://purl.org/dc/terms/"
                   xmlns:dcmitype="http://purl.org/dc/dcmitype/"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Tổng hợp 2 nhiệm vụ chatbot ICTU</dc:title>
  <dc:creator>Codex</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{created_at}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{created_at}</dcterms:modified>
</cp:coreProperties>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types_xml)
        docx.writestr("_rels/.rels", root_rels_xml)
        docx.writestr("docProps/app.xml", app_xml)
        docx.writestr("docProps/core.xml", core_xml)
        docx.writestr("word/document.xml", document_xml)
        docx.writestr("word/styles.xml", styles_xml)
        docx.writestr("word/_rels/document.xml.rels", document_rels_xml)
        for image_path, media_name in media:
            docx.write(image_path, f"word/media/{media_name}")


def _architecture_section_lines(vector_payload: dict, diagram_ref: str) -> list[str]:
    total_files = vector_payload.get("total_files", 0)
    total_chunks = vector_payload.get("total_chunks", 0)
    return [
        "## 7. Nhiệm vụ bổ sung 1 - Bản thiết kế chatbot tổng quát",
        "",
        "- Nhiệm vụ này yêu cầu mô tả được toàn bộ chatbot như một hệ thống hoàn chỉnh, không chỉ là một hàm trả lời đơn lẻ.",
        "- Bản thiết kế được chốt theo hướng agent pipeline: mỗi bước có trách nhiệm riêng, input/output rõ ràng, dễ benchmark và dễ nâng cấp sau này.",
        "- Tài liệu chi tiết đã được viết riêng tại `docs/ai_agent_design.md` để có thể dùng cho cả báo cáo và thuyết trình.",
        "",
        "### 7.1 Sơ đồ tổng quát dựa theo ảnh tham chiếu",
        "",
        f"![Sơ đồ bản thiết kế chatbot tổng quát]({diagram_ref})",
        "",
        "- Sơ đồ được vẽ lại theo bố cục giống ảnh bạn cung cấp: khối RAG nằm ở tầng trên, AI Agent ở giữa, người dùng ở bên trái và các nhánh công cụ hỗ trợ ở bên phải.",
        "- Bên trong khối RAG, truy vấn đi qua các bước Query -> Embedding Model -> Query Embedding -> Vector Database -> Candidate chunks -> Prompt with Context -> LLM.",
        "- Ở tầng dưới, AI Agent làm nhiệm vụ điều phối guardrail, router, tool calling, gọi web search, gọi RAG và trả đáp án về Web UI hoặc API.",
        "- Các nhánh ngoài như Web Search ICTU, External API, Knowledge Base/Upload, Session Memory + Logs cho thấy chatbot không chỉ trả lời từ một model đơn lẻ mà là một hệ thống phối hợp nhiều thành phần.",
        "",
        "### 7.2 Mục tiêu kiến trúc",
        "",
        "- Tiếp nhận câu hỏi từ Web UI và API trong cùng một luồng xử lý thống nhất.",
        "- Tách 3 nhóm tri thức chính để route đúng ngữ cảnh trước khi generate.",
        "- Ưu tiên retrieval có căn cứ, có fallback nhiều lớp và không để câu trả lời trôi ra ngoài phạm vi ICTU.",
        "- Lưu lịch sử chat, session memory, web knowledge cache và log để phục vụ quản trị và cải tiến liên tục.",
        "",
        "### 7.3 Thành phần chính",
        "",
        "- Lớp giao tiếp: `config/app_factory.py`, `controllers/web_controller.py`, `controllers/api_controller.py`.",
        "- Lớp điều phối chat: `services/chat_service.py` và `services/graph_service.py`.",
        "- Lớp truy xuất tri thức: `services/rag_service.py`, `services/vector_store_service.py`, `services/document_service.py`.",
        "- Lớp sinh câu trả lời: `services/multilingual_service.py`, `services/llm_service.py`.",
        "- Lớp lưu vết và bộ nhớ: `config/db.py`, `SESSION_MEMORY`, `logs/`, `reports/generated/`.",
        "",
        "### 7.4 Kho tri thức và storage",
        "",
        f"- Vector layer hiện tại đang quản lý {total_files} file và {total_chunks} chunk có thể truy xuất được.",
        "- Kho tri thức được tách thành `student_handbook_rag`, `school_policy_rag`, `student_faq_rag`.",
        "- Ngoài vector store còn có thêm trusted web knowledge cache và approved Q&A được đưa ngược vào knowledge base.",
        "- Runtime state được lưu trong SQLite để UI, API và benchmark cùng nhìn cùng một nguồn.",
        "",
        "### 7.5 Luồng dữ liệu tổng quát",
        "",
        "- Người dùng gửi câu hỏi -> hệ thống normalize input -> guardrail -> route sang nhóm tri thức -> retrieve -> build prompt -> gọi LLM -> lưu history và memory -> trả kết quả.",
        "- Quản trị viên có thể upload tài liệu, xóa/reset index và duyệt Q&A để cập nhật lại kho tri thức mà không cần sửa tay code xử lý chat.",
        "",
        "### 7.6 Giá trị của bản thiết kế",
        "",
        "- Dễ giải thích chatbot dưới dạng kiến trúc có lớp, có node, có trách nhiệm rõ ràng.",
        "- Dễ map trực tiếp mỗi khối trong báo cáo vào file code thực tế trong repo.",
        "- Dễ mở rộng thành Clarification Agent, Ingestion Agent và Evaluation Agent ở các giai đoạn tiếp theo.",
        "",
    ]


def _framework_section_lines() -> list[str]:
    return [
        "## 8. Nhiệm vụ bổ sung 2 - Framework hỗ trợ cho từng bước xử lý chatbot",
        "",
        "- Framework được hiểu là bộ module và quy tắc hỗ trợ cho từng bước xử lý của chatbot, từ lúc nhận câu hỏi cho tới lúc lưu lại kết quả.",
        "- Mục tiêu của phần này là chứng minh rằng mỗi bước đều đã có thành phần code tương ứng, không phải mô tả ý tưởng chung chung.",
        "",
        "### 8.1 Chuỗi xử lý đề xuất",
        "",
        "1. Tiếp nhận request: FastAPI + controllers nhận Web/API payload và đưa vào chat service.",
        "2. Chuẩn hóa input: `_normalize_input` làm sạch message, chốt `session_id`, `language`, `selected_llm_model`.",
        "3. Lưu message người dùng: `_persist_user_message` ghi lịch sử vào SQLite trước khi xử lý tiếp.",
        "4. Guardrail và quick reply: `_handle_guardrails` xử lý swear word, lời chào, trường hợp không cần retrieval.",
        "5. Route RAG: `_route_rag` gọi `route_rag_tool` để chọn `student_handbook_rag`, `school_policy_rag`, `student_faq_rag` hoặc fallback.",
        "6. Tạo retrieval query: `build_retrieval_query` ghép câu hỏi hiện tại với memory của phiên.",
        "7. Scope check: `is_ictu_related_query` chặn câu hỏi ngoài phạm vi ICTU.",
        "8. Web knowledge cache: ưu tiên kết quả đã lưu và đã được xác minh trước đó nếu có.",
        "9. Local corpus retrieval: tìm trong kho tri thức đúng nhóm để lấy ngữ cảnh chính.",
        "10. General fallback retrieval: dùng vector, hybrid và lexical để cứu các ca route mơ hồ hoặc dữ liệu chưa đều.",
        "11. Web search bổ sung: chỉ gọi khi cần dữ liệu mới và ưu tiên domain ICTU.",
        "12. Prompt builder + generation: `chat_multilingual` đóng gói ngữ cảnh, giữ ngôn ngữ phiên và gọi LLM có fallback model.",
        "13. Finalize: lưu bot reply, cập nhật session memory và save web answer nếu câu trả lời đến từ web search.",
        "",
        "### 8.2 Framework support theo từng nhóm bước",
        "",
        "- Giao tiếp và session: `config/middleware.py`, `config/db.py`, `controllers/*`.",
        "- Điều phối pipeline: `services/chat_service.py`, `services/graph_service.py`.",
        "- Retrieval và evidence: `services/rag_service.py`, `services/vector_store_service.py`, `services/web_search.py`, `services/web_knowledge_service.py`.",
        "- Prompt và generation: `services/multilingual_service.py`, `services/llm_service.py`.",
        "- Quản trị dữ liệu: `services/document_service.py`, `services/knowledge_base_service.py`.",
        "- Đo lường chất lượng: `tools/evaluation/evaluate_chatbot.py`, `tools/evaluation/analyze_dataset.py`, unittest trong `tests/`.",
        "",
        "### 8.3 Input, output và fallback của framework",
        "",
        "- Input của framework là `message`, `session_id`, `selected_model` và kho tri thức đã index.",
        "- Output là `response`, `sources`, `rag_tool`, `rag_route`, `chunks_used`, `llm_model`.",
        "- Fallback được đặt ở nhiều tầng: quick reply, keyword router, general retrieval, web cache, web search, model rotation.",
        "- Nhiều tầng fallback này là điểm mạnh để chatbot không bị vỡ toàn bộ pipeline khi một thành phần phụ trợ gặp lỗi.",
        "",
        "### 8.4 Cách chứng minh framework đang hoạt động",
        "",
        "- Benchmark hiện tại đo được route accuracy, source hit rate, top-1 hit rate và MRR nên phần route + retrieval đã có minh chứng định lượng.",
        "- Unittest bảo vệ các điểm dễ vỡ như model rotation, upload flow, prompt builder, web knowledge cache và vector payload.",
        "- Tài liệu `docs/ai_agent_design.md` đã map trực tiếp mỗi bước xử lý với hàm/module thật trong codebase.",
        "",
    ]


def _build_report_markdown(
    dataset_report: dict,
    eval_report: dict,
    unittest_report: dict,
    vector_payload: dict,
    diagram_ref: str,
) -> str:
    longest_title = dataset_report["title_stats"]["longest_sample"]
    longest_content = dataset_report["content_stats"]["longest_sample"]
    generated_at = _format_date(datetime.now().astimezone().isoformat())

    lines = [
        "# Tổng hợp 2 nhiệm vụ chatbot ICTU",
        "",
        f"- Ngày tổng hợp: {generated_at}",
        f"- Corpus phân tích: {dataset_report['corpus_root']}",
        "- Mục tiêu tài liệu này là gộp cả 2 nhiệm vụ đã làm vào cùng một file DOCX và chèn luôn sơ đồ bản thiết kế chatbot tổng quát.",
        "",
        "## 1. Mục tiêu đợt review",
        "",
        "- Review lại dự án theo đề cương PDF.",
        "- Xác định mức tiến độ hiện tại.",
        "- Chốt lại benchmark, test và tài liệu tổng hợp.",
        "- Bổ sung chi tiết cho 2 nhiệm vụ: bản thiết kế chatbot tổng quát và framework hỗ trợ cho từng bước xử lý chatbot.",
        "",
        "## 2. Các đầu mục đã hoàn thành",
        "",
        "- Đã rà soát cấu trúc dự án chatbot/RAG và xác định kiến trúc pipeline-agent hiện tại.",
        "- Đã phân tích corpus trong `data/qa_generated_fixed` theo số mẫu, độ dài title, độ dài content và phân bố nhóm tri thức.",
        "- Đã tạo và duy trì bộ benchmark tại `evaluation/chatbot_eval_dataset.json` để đo router và retrieval.",
        "- Đã chạy lại benchmark hệ thống và lưu kết quả vào `reports/generated/eval_results.*`.",
        "- Đã chạy unit test và lưu tổng hợp vào `reports/generated/unittest_summary.json`.",
        "- Đã viết lại tài liệu thiết kế chi tiết tại `docs/ai_agent_design.md`.",
        "- Đã vẽ thêm sơ đồ tổng quát chatbot theo phong cách của ảnh tham chiếu người dùng cung cấp.",
        "- Đã cấu hình sinh báo cáo `.md` và `.docx` đồng bộ từ script này, trong đó DOCX có nhúng ảnh sơ đồ.",
        "",
        "## 3. Tổng quan hệ thống hiện tại",
        "",
        "- Đây là chatbot RAG cho ICTU với Web UI, REST API, knowledge base và các trang quản trị dữ liệu.",
        "- Luồng xử lý chính hiện tại là normalize -> guardrail -> route RAG -> retrieve -> generate -> finalize.",
        "- Hệ thống đã tách 3 nhóm tri thức chính để tránh trộn tất cả dữ liệu vào một kho duy nhất.",
        "- Wrapper graph trong `services/graph_service.py` cho phép giải thích hệ thống dưới dạng agent pipeline, đồng thời vẫn có sequential fallback.",
        "",
        "## 4. Kết quả phân tích dữ liệu",
        "",
        f"- Tổng số mẫu dữ liệu: {dataset_report['total_samples']}.",
        f"- Tổng số cặp Q/A: {dataset_report['total_qa_pairs']}.",
        f"- Title trung bình: {dataset_report['title_stats']['chars']['avg']} ký tự, min {dataset_report['title_stats']['chars']['min']}, max {dataset_report['title_stats']['chars']['max']}.",
        f"- Content trung bình: {dataset_report['content_stats']['chars']['avg']} ký tự, min {dataset_report['content_stats']['chars']['min']}, max {dataset_report['content_stats']['chars']['max']}.",
        f"- File có title dài nhất: {longest_title['path']} ({longest_title['title_chars']} ký tự).",
        f"- File có content dài nhất: {longest_content['path']} ({longest_content['content_chars']} ký tự).",
        "",
        "### Phân bố theo nhóm tri thức",
        "",
    ]

    for tool_name, count in dataset_report["tool_distribution"].items():
        lines.append(f"- {tool_name}: {count} mẫu.")

    lines.extend(
        [
            "",
            "## 5. Kết quả benchmark và test",
            "",
            f"- Số câu hỏi benchmark: {eval_report['total_cases']}.",
            f"- Số ca có nhãn nguồn để đo retrieval: {eval_report['labeled_source_cases']}.",
            f"- Route accuracy: {_format_pct(eval_report['route_accuracy'])}.",
            f"- Source hit rate: {_format_pct(eval_report['source_hit_rate'])}.",
            f"- Source top-1 hit rate: {_format_pct(eval_report['source_top1_hit_rate'])}.",
            f"- Source MRR: {eval_report['source_mrr']}.",
            f"- Độ trễ trung bình: {eval_report['avg_latency_ms']} ms.",
            f"- Số chunk trung bình mỗi truy vấn: {eval_report['avg_chunks_used']}.",
            f"- Route backend phân bố: {_join_distribution(eval_report['route_prefix_distribution'])}.",
            f"- Failing case: {len(eval_report['failing_cases'])}.",
            f"- Unittest: {unittest_report['tests_ran']} test, trạng thái {unittest_report['status']}, thời gian {unittest_report['duration_seconds']} giây.",
            "",
            "## 6. Nhận định tiến độ",
            "",
            "- Theo lịch 10 tuần trong đề cương, mốc review 16/04/2026 nằm trong tuần 6.",
            "- Theo mức độ hoàn thành deliverable thực tế trong repo, dự án đã ở mặt bằng week 9 hoàn thành và week 10 đang hoàn thiện.",
            "- Đồ án đã có code chạy được, benchmark, unit test, tài liệu tổng hợp và artefact phục vụ demo.",
            "",
        ]
    )

    lines.extend(_architecture_section_lines(vector_payload, diagram_ref))
    lines.extend(_framework_section_lines())

    lines.extend(
        [
            "## 9. Khoảng cách còn lại so với đề cương",
            "",
            "- Vector backend hiện tại vẫn là `ChromaDB`, trong khi đề cương nêu `FAISS`.",
            "- Tên nhóm tool chưa map sát 100% với cách đặt tên nghiệp vụ trong đề cương.",
            "- Vẫn còn một số dấu vết legacy và vấn đề encoding cần dọn thêm để báo cáo đẹp hơn.",
            "- Chưa có smoke test UI/startup rõ ràng cho nhánh demo production-like.",
            "",
            "## 10. Tệp bàn giao",
            "",
            "- `docs/ai_agent_design.md`: tài liệu chi tiết cho 2 nhiệm vụ bổ sung.",
            "- `reports/bao_cao_nhiem_vu_chatbot.md`: bản Markdown nguồn.",
            "- `reports/bao_cao_nhiem_vu_chatbot.docx`: file DOCX đã gộp 2 nhiệm vụ.",
            "- `reports/generated/assignment_chatbot_diagrams/chatbot_tong_quat_chi_tiet.png`: sơ đồ thiết kế chatbot tổng quát.",
            "- `reports/generated/dataset_analysis.json`: thống kê corpus.",
            "- `reports/generated/eval_results.json`: kết quả benchmark.",
            "- `reports/generated/unittest_summary.json`: tổng hợp unit test.",
            "",
            "## 11. Kết luận ngắn",
            "",
            "- Hai nhiệm vụ bổ sung đã được gộp vào cùng một file DOCX, thay vì tách rời từng phần riêng lẻ.",
            "- Sơ đồ mới giúp phần 'bản thiết kế chatbot tổng quát' trực quan hơn, bám theo bố cục ảnh tham chiếu nhưng đã chuyển thành đúng hệ thống ICTU hiện tại.",
            "- Framework từng bước giúp đối chiếu mỗi bước xử lý với hàm/module thật trong repo, rất hợp để đưa vào báo cáo và slide bảo vệ.",
            "",
            "## 12. Đoạn kết luận dùng để nộp",
            "",
            "### 12.1 Bản dùng cho báo cáo",
            "",
            "Qua quá trình đối chiếu giữa tài liệu thiết kế, mã nguồn triển khai, sơ đồ hệ thống, kết quả benchmark và bộ unit test, có thể kết luận rằng hai nhiệm vụ \"bản thiết kế chatbot tổng quát\" và \"framework hỗ trợ cho từng bước xử lý chatbot\" đã được hoàn thành ở mức có thể sử dụng trực tiếp trong báo cáo và buổi bảo vệ. Bản thiết kế chatbot tổng quát đã mô tả rõ các thành phần chính của hệ thống, bao gồm lớp giao tiếp Web/API, lớp điều phối hội thoại, lớp truy xuất tri thức, lớp sinh câu trả lời và lớp lưu vết bộ nhớ; đồng thời thể hiện được mối liên hệ giữa người dùng, AI Agent, RAG pipeline, vector store, SQLite, web knowledge cache và LLM. Nhờ đó, chatbot không còn được trình bày như một hàm trả lời đơn lẻ mà đã được mô hình hóa như một hệ thống hoàn chỉnh, có kiến trúc rõ ràng và có khả năng mở rộng.",
            "",
            "Ở nhiệm vụ thứ hai, framework xử lý chatbot đã được mô tả theo đúng chuỗi bước thực thi của hệ thống hiện tại: tiếp nhận request, chuẩn hóa input, lưu lịch sử hội thoại, guardrail, định tuyến nhóm tri thức, tạo retrieval query, kiểm tra phạm vi ICTU, truy xuất ngữ cảnh, sinh câu trả lời, lưu phản hồi và cập nhật session memory. Điểm quan trọng là mỗi bước đều đã được gắn với hàm hoặc module cụ thể trong codebase để chứng minh đây là framework đang vận hành thật, không chỉ là sơ đồ ý tưởng. Bên cạnh đó, benchmark và unit test đóng vai trò minh chứng định lượng cho chất lượng router, retrieval, fallback và prompt pipeline. Vì vậy, trong phạm vi hai nhiệm vụ được giao, có thể chốt rằng sản phẩm đã hoàn thành phần nội dung cốt lõi, đủ cơ sở để đưa vào báo cáo học phần, thuyết trình demo và làm nền cho các bước mở rộng tiếp theo như Clarification Agent, Ingestion Agent hoặc Evaluation Agent.",
            "",
            "### 12.2 Bản rút gọn cho slide hoặc phần trình bày miệng",
            "",
            "- Hai nhiệm vụ đã hoàn thành không chỉ ở mức mô tả ý tưởng mà đã có tài liệu, sơ đồ, code triển khai và kết quả test để minh chứng.",
            "- Bản thiết kế chatbot tổng quát đã thể hiện được đầy đủ kiến trúc hệ thống và mối liên kết giữa Web/API, RAG, vector store, memory, logging và LLM.",
            "- Framework xử lý chatbot đã bám sát luồng chạy thực tế của hệ thống, mỗi bước đều map được với module hoặc hàm cụ thể trong repo.",
            "- Với trạng thái hiện tại, phần nội dung này đã đủ dùng cho báo cáo và bảo vệ; các phần còn lại chủ yếu là nâng cấp thêm để hoàn thiện hơn chứ không còn là thiếu đầu việc chính.",
            "",
        ]
    )

    if unittest_report["warnings"]:
        lines.extend(["### Cảnh báo từ lần chạy test", ""])
        for warning in unittest_report["warnings"]:
            lines.append(f"- {warning}")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    diagram_assets = generate_diagram_assets()
    diagram_ref = diagram_assets["general_design_png"].relative_to(ROOT).as_posix()

    dataset_report = _run_analysis()
    eval_report = _run_evaluation()
    unittest_report = _run_unittest()
    vector_payload = get_vector_manager_payload(limit_per_file=2)

    report_markdown = _build_report_markdown(
        dataset_report=dataset_report,
        eval_report=eval_report,
        unittest_report=unittest_report,
        vector_payload=vector_payload,
        diagram_ref=diagram_ref,
    )

    REPORT_MD_PATH.write_text(report_markdown, encoding="utf-8")
    _build_docx(report_markdown, REPORT_DOCX_PATH)

    print(
        json.dumps(
            {
                "status": "ok",
                "report_md": str(REPORT_MD_PATH),
                "report_docx": str(REPORT_DOCX_PATH),
                "diagram_png": str(diagram_assets["general_design_png"]),
                "dataset_analysis_json": str(GENERATED_DIR / "dataset_analysis.json"),
                "eval_results_json": str(GENERATED_DIR / "eval_results.json"),
                "unittest_summary_json": str(UNITTEST_JSON_PATH),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
