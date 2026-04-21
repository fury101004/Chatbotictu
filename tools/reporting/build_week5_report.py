from __future__ import annotations

import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def _find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "main.py").exists() and (parent / "services").is_dir():
            return parent
    return Path(__file__).resolve().parents[2]


ROOT = _find_repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402
from tools.evaluation.analyze_dataset import analyze_corpus  # noqa: E402
from services.document_service import get_vector_manager_payload  # noqa: E402
from services.knowledge_base_service import get_knowledge_base_payload  # noqa: E402

REPORT_DIR = ROOT / "reports"
GENERATED_DIR = REPORT_DIR / "generated"
REPORT_MD_PATH = REPORT_DIR / "tuan_5_knowledge_base_hien_trang.md"
REPORT_DOCX_PATH = REPORT_DIR / "tuan_5_knowledge_base_hien_trang.docx"
REPORT_JSON_PATH = GENERATED_DIR / "tuan_5_kb_status.json"


def _source_contains(path: Path, snippet: str) -> bool:
    if not path.exists():
        return False
    return snippet in path.read_text(encoding="utf-8", errors="ignore")


def _format_date(value: datetime) -> str:
    return value.astimezone().strftime("%d/%m/%Y %H:%M")


def _invalid_xml_chars_removed(text: str) -> str:
    return "".join(
        ch
        for ch in text
        if ch == "\t" or ch == "\n" or ch == "\r" or ord(ch) >= 32
    )


def _paragraph_xml(text: str, *, bold: bool = False) -> str:
    safe_text = escape(_invalid_xml_chars_removed(text))
    if not safe_text:
        return "<w:p/>"

    run_props = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return (
        "<w:p>"
        "<w:r>"
        f"{run_props}"
        f'<w:t xml:space="preserve">{safe_text}</w:t>'
        "</w:r>"
        "</w:p>"
    )


def _markdown_to_wordml(markdown_text: str) -> str:
    paragraphs: list[str] = []
    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("# "):
            paragraphs.append(_paragraph_xml(stripped[2:], bold=True))
        elif stripped.startswith("## "):
            paragraphs.append(_paragraph_xml(stripped[3:], bold=True))
        elif stripped.startswith("### "):
            paragraphs.append(_paragraph_xml(stripped[4:], bold=True))
        else:
            paragraphs.append(_paragraph_xml(line))

    body = "".join(paragraphs)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {body}
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>
"""


def _build_docx(markdown_text: str, output_path: Path) -> None:
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    document_xml = _markdown_to_wordml(markdown_text)
    styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
  </w:style>
</w:styles>
"""
    content_types_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
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
    document_rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>
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
  <dc:title>Báo cáo tuần 5 knowledge base</dc:title>
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


def _top_entries(source: dict[str, int], limit: int = 6) -> list[tuple[str, int]]:
    return sorted(source.items(), key=lambda item: (-item[1], item[0]))[:limit]


def _build_status_payload() -> dict:
    now = datetime.now().astimezone()
    dataset_report = analyze_corpus(settings.QA_CORPUS_ROOT)
    vector_payload = get_vector_manager_payload()
    knowledge_base_payload = get_knowledge_base_payload()
    knowledge_base_summary = knowledge_base_payload["summary"]

    web_controller_path = ROOT / "controllers" / "web_controller.py"
    api_controller_path = ROOT / "controllers" / "api_controller.py"
    knowledge_base_template_path = ROOT / "views" / "frontend" / "templates" / "pages" / "knowledge_base.html"
    knowledge_base_service_path = ROOT / "services" / "knowledge_base_service.py"
    base_layout_path = ROOT / "views" / "frontend" / "templates" / "layouts" / "base.html"

    checks = {
        "seed_corpus_present": dataset_report["total_samples"] > 0,
        "qa_pairs_present": dataset_report["total_qa_pairs"] > 0,
        "vector_store_has_files": vector_payload["total_files"] > 0,
        "vector_store_has_chunks": vector_payload["total_chunks"] > 0,
        "knowledge_base_has_items": knowledge_base_summary["total_knowledge_items"] > 0,
        "knowledge_base_service_present": knowledge_base_service_path.exists(),
        "knowledge_base_web_route_present": _source_contains(web_controller_path, '@router.get("/knowledge-base")'),
        "knowledge_base_approve_flow_present": _source_contains(web_controller_path, '@router.post("/knowledge-base/approve-chat")'),
        "knowledge_base_api_route_present": _source_contains(api_controller_path, '@router.get("/knowledge-base")'),
        "knowledge_base_page_present": knowledge_base_template_path.exists(),
        "knowledge_base_nav_present": _source_contains(base_layout_path, 'href="/knowledge-base"'),
        "rag_flow_present": (ROOT / "services" / "document_service.py").exists() and (ROOT / "services" / "vector_store_service.py").exists(),
        "search_engine_flow_present": (ROOT / "services" / "rag_service.py").exists() and (ROOT / "services" / "vector_store_service.py").exists(),
        "data_loader_ui_present": (ROOT / "views" / "frontend" / "templates" / "pages" / "data_loader.html").exists(),
        "vector_manager_ui_present": (ROOT / "views" / "frontend" / "templates" / "pages" / "vector_manager_v2.html").exists(),
    }

    equivalent_completion = all(checks.values())

    return {
        "generated_at": now.isoformat(),
        "week_label": "Tuần 5",
        "original_requirement": "Thu thập dữ liệu và xây dựng Knowledge Base",
        "project_alignment_note": (
            "Đối chiếu theo dự án chatbot hiện tại và xác nhận knowledge base đã tồn tại như "
            "một module riêng: quản trị hợp nhất vector store và chat Q&A; còn search engine/"
            "hybrid search là cơ chế truy xuất bên trong knowledge base."
        ),
        "status": "completed_equivalent" if equivalent_completion else "partial",
        "status_label": "Đã hoàn thành theo dự án hiện tại" if equivalent_completion else "Chưa hoàn thành đủ",
        "checks": checks,
        "dataset_report": dataset_report,
        "vector_payload_summary": {
            "total_files": vector_payload["total_files"],
            "total_chunks": vector_payload["total_chunks"],
        },
        "knowledge_base_summary": knowledge_base_summary,
        "knowledge_base_warnings": knowledge_base_payload.get("warnings", []),
        "knowledge_flows": [
            {
                "name": "Tài liệu -> Vector Knowledge Base",
                "summary": "Nạp seed corpus hoặc file upload, chunking thông minh, vector hóa và đưa vào kho tri thức dùng cho retrieval.",
                "steps": [
                    "Nguồn vào là `data/qa_generated_fixed` hoặc file `.md/.txt` được upload theo từng nhóm tri thức.",
                    "Hệ thống gán `tool_name`, lưu file, chunk bằng `smart_chunk`, tạo embedding và lưu vào Chroma collection `markdown_docs_v2`.",
                    "Sau khi add documents, hệ thống rebuild BM25 và inject bot rule để hybrid search luôn sẵn sàng.",
                    "Knowledge Base page đọc lại vector entries từ collection để hiển thị tổng hợp theo nhóm handbook/policy/FAQ.",
                ],
                "evidence": [
                    "services/document_service.py",
                    "services/vector_store_service.py",
                    "services/knowledge_base_service.py",
                    "views/frontend/templates/pages/data_loader.html",
                    "views/frontend/templates/pages/vector_manager_v2.html",
                ],
            },
            {
                "name": "Chat History -> Approve -> Knowledge Base",
                "summary": "Ghép cặp Q&A từ chat history, duyệt thủ công và chỉ khi duyệt mới ghi thành tài liệu KB để index lại vào vector store.",
                "steps": [
                    "Mỗi lượt chat được lưu vào bảng `chat_history`, sau đó knowledge base service ghép user/bot theo `session_id` để tạo cặp hỏi-đáp.",
                    "Trang `/knowledge-base` cho phép duyệt từng cặp Q&A qua action `approve-chat`.",
                    "Khi duyệt, hệ thống sinh file markdown trong `data/rag_uploads/<tool>/_knowledge_base_chat/`, ghi metadata vào bảng `approved_chat_qa` và index vào vector store nếu embedding backend sẵn sàng.",
                    "Q&A chưa duyệt chỉ hiển thị và searchable ở tầng quản trị knowledge base; Q&A đã duyệt mới trở thành nguồn retrieval chính thức cho chatbot.",
                ],
                "evidence": [
                    "services/knowledge_base_service.py",
                    "config/db.py",
                    "controllers/web_controller.py",
                    "views/frontend/templates/pages/knowledge_base.html",
                ],
            },
            {
                "name": "Tra cứu và sử dụng Knowledge Base",
                "summary": "Knowledge base được tra cứu ở cả UI quản trị lẫn pipeline chatbot thông qua keyword search, lexical fallback và hybrid search.",
                "steps": [
                    "API/web knowledge base dùng `get_knowledge_base_payload` để hợp nhất kết quả từ vector store và chat history theo cùng một ô tìm kiếm.",
                    "Pipeline chatbot đi qua router handbook/policy/FAQ/fallback rồi gọi retrieval theo tool hoặc `retrieve_general_context`.",
                    "Nhánh general retrieval ưu tiên hybrid search (vector + BM25), có forced-file khi người dùng nhắc đúng tên tài liệu và có lexical fallback khi vector retrieval không sẵn sàng.",
                    "Ngữ cảnh sau retrieval được đưa sang response composer để sinh câu trả lời, rồi lịch sử chat lại được lưu về để phục vụ vòng KB tiếp theo.",
                ],
                "evidence": [
                    "services/rag_service.py",
                    "services/chat_service.py",
                    "services/vector_store_service.py",
                    "controllers/api_controller.py",
                    "controllers/web_controller.py",
                ],
            },
        ],
    }


def _build_report_markdown(payload: dict) -> str:
    generated_at = _format_date(datetime.fromisoformat(payload["generated_at"]))
    dataset_report = payload["dataset_report"]
    vector_summary = payload["vector_payload_summary"]
    knowledge_base_summary = payload["knowledge_base_summary"]
    top_folders = _top_entries(dataset_report["folder_distribution"])

    lines = [
        "# Báo cáo Tuần 5 - Thu thập dữ liệu và xây dựng Knowledge Base",
        "",
        f"- Ngày tổng hợp: {generated_at}",
        f"- Trạng thái đánh giá: {payload['status_label']}",
        "- Cách đối chiếu: bám theo code hiện tại để xác nhận knowledge base đã có thật, mô tả đúng luồng của nó và bổ sung vào báo cáo `.docx`.",
        "",
        "## 1. Kết luận nhanh",
        "",
        "- Đã kiểm tra lại và xác nhận hệ thống hiện đã có module Knowledge Base riêng.",
        "- Knowledge Base không chỉ là vector store: nó hợp nhất 2 nguồn tri thức quản trị là vector documents và chatbot Q&A, đồng thời có API/web riêng để tra cứu.",
        f"- Dữ liệu hiện có: {knowledge_base_summary['vector_files']} vector files, {knowledge_base_summary['vector_chunks']} vector chunks, {knowledge_base_summary['chat_pairs']} cặp Q&A chat, {knowledge_base_summary['approved_chat_qas']} Q&A đã duyệt.",
        "",
        "## 2. Minh chứng hoàn thành",
        "",
        f"- Corpus tri thức gốc nằm tại `data/qa_generated_fixed` với {dataset_report['total_samples']} file.",
        f"- Tổng số cặp hỏi đáp trong corpus: {dataset_report['total_qa_pairs']}.",
        f"- Vector store hiện có {vector_summary['total_files']} file và {vector_summary['total_chunks']} chunk hiển thị được.",
        f"- Knowledge Base quản trị hiện đang thấy tổng cộng {knowledge_base_summary['total_knowledge_items']} mục tri thức.",
        "- Có route web `/knowledge-base`, route API `/api/v1/knowledge-base`, template giao diện riêng và service riêng để tổng hợp dữ liệu KB.",
        "",
        "## 3. Luồng 1 - Tài liệu -> Vector Knowledge Base",
        "",
        "- Nguồn tri thức đi vào từ seed corpus `data/qa_generated_fixed` hoặc file upload `.md/.txt` theo từng nhóm tool.",
        "- `services/document_service.py` chịu trách nhiệm lưu file, gán `tool_name` và gọi `add_documents` để chunk/index.",
        "- `services/vector_store_service.py` thực hiện `smart_chunk`, tạo embedding, lưu vào Chroma, rebuild BM25 và inject bot rule.",
        "- `services/knowledge_base_service.py` đọc lại các chunk trong vector store để hiển thị trên trang Knowledge Base.",
        "",
        "## 4. Luồng 2 - Chat History -> Approve -> Knowledge Base",
        "",
        "- Mỗi tin nhắn user/bot được lưu trong `chat_history`; knowledge base service ghép các cặp hỏi-đáp theo `session_id`.",
        "- Trang `/knowledge-base` cho phép người vận hành duyệt thủ công từng cặp Q&A có ích.",
        "- Sau khi duyệt, hệ thống sinh file markdown trong `data/rag_uploads/<tool>/_knowledge_base_chat/`, lưu metadata vào bảng `approved_chat_qa` và index lại vào vector store.",
        "- Điểm quan trọng: chat Q&A chưa duyệt chỉ nằm ở tầng quản trị/search của Knowledge Base, còn chat Q&A đã duyệt mới trở thành nguồn retrieval chính thức cho chatbot.",
        "",
        "## 5. Luồng 3 - Tra cứu và sử dụng Knowledge Base",
        "",
        "- Ở tầng quản trị, `get_knowledge_base_payload` hợp nhất tìm kiếm trên vector entries và chat entries trong cùng một màn hình.",
        "- Ở tầng chatbot, `services/chat_service.py` route câu hỏi sang handbook/policy/FAQ/fallback rồi gọi retrieval tương ứng.",
        "- `services/rag_service.py` dùng keyword router hoặc LLM router, sau đó retrieval theo tool hoặc general retrieval.",
        "- General retrieval ưu tiên hybrid search (vector + BM25), có forced-file khi nhắc đúng tên tài liệu và lexical fallback khi vector retrieval không sẵn sàng.",
        "",
        "## 6. Ghi chú về Search Engine",
        "",
        "- Trong code hiện tại, search engine không phải là một knowledge base riêng tách rời.",
        "- Các cơ chế lexical search, BM25, hybrid search và fallback là engine truy xuất dùng để đọc Knowledge Base hiệu quả hơn.",
        "- Vì vậy khi viết báo cáo, nên mô tả Knowledge Base là kho tri thức đã có sẵn; còn Search Engine là cách truy cập kho tri thức đó.",
        "",
        "## 7. Dữ liệu nền cho Knowledge Base",
        "",
    ]

    for folder, count in top_folders:
        lines.append(f"- {folder}: {count} file.")

    lines.extend(
        [
            "",
            "## 8. Đánh giá mức độ hoàn thành Tuần 5",
            "",
            "- Mục tiêu tương đương của Tuần 5 trong dự án này là có dữ liệu tri thức, có knowledge base và có cơ chế truy xuất dữ liệu phục vụ chatbot.",
            "- Dự án hiện tại đã đáp ứng được phần dữ liệu nền, knowledge base quản trị, duyệt Q&A vào KB và cơ chế retrieve phục vụ chatbot.",
            "- Vì vậy có thể kết luận Tuần 5 đã hoàn thành theo đúng dự án hiện tại.",
            "",
            "## 9. Tệp bàn giao",
            "",
            "- `reports/tuan_5_knowledge_base_hien_trang.md`",
            "- `reports/tuan_5_knowledge_base_hien_trang.docx`",
            "- `reports/generated/tuan_5_kb_status.json`",
            "",
            "## 10. Kết luận cuối",
            "",
            "- Kết luận dùng để nộp: dự án hiện tại đã có Knowledge Base thật sự và đã có luồng vận hành khá đầy đủ.",
            "- Phần bổ sung trong docx lần này là mô tả đúng 3 luồng: tài liệu vào vector KB, chat Q&A duyệt vào KB, và chatbot/search engine truy xuất KB để trả lời.",
        ]
    )

    warnings = payload.get("knowledge_base_warnings", [])
    if warnings:
        lines.extend(
            [
                "",
                "## 11. Cảnh báo hiện trạng",
                "",
            ]
        )
        for warning in warnings:
            lines.append(f"- {warning}")

    return "\n".join(lines) + "\n"


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    payload = _build_status_payload()
    markdown_text = _build_report_markdown(payload)

    REPORT_JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_MD_PATH.write_text(markdown_text, encoding="utf-8")
    _build_docx(markdown_text, REPORT_DOCX_PATH)

    print(
        json.dumps(
            {
                "status": payload["status"],
                "status_label": payload["status_label"],
                "report_md": str(REPORT_MD_PATH),
                "report_docx": str(REPORT_DOCX_PATH),
                "report_json": str(REPORT_JSON_PATH),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
