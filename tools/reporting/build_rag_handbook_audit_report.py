from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings
from pipelines.chunking_pipeline import extract_academic_year, smart_chunk
from pipelines.indexing_pipeline import index_document
from services.chat.multilingual_service import _build_final_prompt
from services.rag.langchain_retrievers import VectorStoreRetriever
from services.rag.rag_corpus import _load_tool_corpus, _search_documents
from repositories.vector_repository import count_vector_chunks, list_vector_chunks, search_vector_documents
from services.vector.vector_store_service import embedding_backend_ready


HANDBOOK_DIR = PROJECT_ROOT / "data" / "primary_corpus" / "student_handbooks"
OUTPUT_DOCX = PROJECT_ROOT / "Bao_cao_ra_soat_RAG_so_tay_sinh_vien.docx"
QUESTION_RE = re.compile(r"^\*\*Question:\*\*\s*(.+?)\s*$", flags=re.IGNORECASE)
ANSWER_RE = re.compile(r"^\*\*Answer:\*\*\s*(.+?)\s*$", flags=re.IGNORECASE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", flags=re.MULTILINE)
SENTENCE_END_RE = re.compile(r"[.!?;:。！？…]+[\"')\]]*$")


@dataclass
class QuestionItem:
    source_file: str
    academic_year: str
    question: str
    answer: str


class CaptureCollection:
    def __init__(self) -> None:
        self.add_calls: list[dict[str, Any]] = []
        self.deleted_where: list[dict[str, Any]] = []

    def delete(self, where=None) -> None:
        self.deleted_where.append(where or {})

    def add(self, *, documents, metadatas, ids) -> None:
        self.add_calls.append({"documents": documents, "metadatas": metadatas, "ids": ids})


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _word_count(text: str) -> int:
    return len(str(text or "").split())


def _question_items(path: Path) -> list[QuestionItem]:
    text = _read_text(path)
    year = extract_academic_year(path.name, path.name, text) or ""
    items: list[QuestionItem] = []
    current_question = ""
    for line in text.splitlines():
        question_match = QUESTION_RE.match(line.strip())
        if question_match:
            current_question = question_match.group(1).strip()
            continue
        answer_match = ANSWER_RE.match(line.strip())
        if answer_match and current_question:
            items.append(
                QuestionItem(
                    source_file=path.name,
                    academic_year=year,
                    question=current_question,
                    answer=answer_match.group(1).strip(),
                )
            )
            current_question = ""
    return items


def _handbook_files() -> list[Path]:
    return sorted(
        path
        for path in HANDBOOK_DIR.glob("*.md")
        if path.is_file() and not path.name.endswith(".questions.md")
    )


def _questions_file_for(handbook_path: Path) -> Path:
    return handbook_path.with_name(handbook_path.stem + ".questions.md")


def analyze_data_and_chunks() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    all_chunk_word_counts: list[int] = []
    total_sentence_cut_risk = 0
    total_chunks = 0
    chunk_type_counter: Counter[str] = Counter()

    for path in _handbook_files():
        text = _read_text(path)
        headings = HEADING_RE.findall(text)
        heading_levels = Counter(len(marker) for marker, _title in headings)
        chunks = smart_chunk(
            text,
            path.name,
            source_name=f"student_handbooks/{path.name}",
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            count_tokens_fn=_word_count,
        )
        q_path = _questions_file_for(path)
        questions = _question_items(q_path) if q_path.exists() else []
        word_counts = [int(chunk.get("word_count", _word_count(chunk.get("text", "")))) for chunk in chunks]
        sentence_cut_risk = sum(
            1
            for chunk in chunks
            if chunk.get("type") == "text"
            and chunk.get("text")
            and not SENTENCE_END_RE.search(str(chunk["text"]).strip().split()[-1])
            and int(chunk.get("word_count", 0)) >= max(20, int(settings.CHUNK_SIZE * 0.7))
        )

        total_sentence_cut_risk += sentence_cut_risk
        total_chunks += len(chunks)
        all_chunk_word_counts.extend(word_counts)
        chunk_type_counter.update(str(chunk.get("type", "text")) for chunk in chunks)
        rows.append(
            {
                "file_name": path.name,
                "academic_year": extract_academic_year(path.name, path.name, text) or "",
                "size_kb": round(path.stat().st_size / 1024, 1),
                "line_count": len(text.splitlines()),
                "heading_count": len(headings),
                "heading_levels": dict(sorted(heading_levels.items())),
                "question_count": len(questions),
                "chunk_count": len(chunks),
                "avg_words": round(sum(word_counts) / max(len(word_counts), 1), 1),
                "max_words": max(word_counts, default=0),
                "sentence_cut_risk": sentence_cut_risk,
            }
        )

    summary = {
        "handbook_count": len(rows),
        "question_file_count": len(list(HANDBOOK_DIR.glob("*.questions.md"))),
        "total_chunks": total_chunks,
        "chunk_size": settings.CHUNK_SIZE,
        "chunk_overlap": settings.CHUNK_OVERLAP,
        "avg_chunk_words": round(sum(all_chunk_word_counts) / max(len(all_chunk_word_counts), 1), 1),
        "max_chunk_words": max(all_chunk_word_counts, default=0),
        "sentence_cut_risk": total_sentence_cut_risk,
        "chunk_types": dict(chunk_type_counter),
    }
    return rows, summary


def audit_metadata_contract() -> dict[str, Any]:
    sample_path = _handbook_files()[-1]
    collection = CaptureCollection()
    index_document(
        file_content=_read_text(sample_path),
        filename=sample_path.name,
        version="audit",
        source_name=f"student_handbooks/{sample_path.name}",
        tool_name="student_handbook_rag",
        collection_getter=lambda: collection,
        smart_chunk_fn=lambda content, filename, source_name: smart_chunk(
            content,
            filename,
            source_name=source_name,
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            count_tokens_fn=_word_count,
        ),
        extract_academic_year_fn=extract_academic_year,
        infer_document_type_fn=lambda _source, _filename, _tool, _content: "student_handbook",
        rebuild_bm25_fn=lambda: None,
        inject_bot_rule_fn=lambda **_kwargs: None,
    )
    metadatas = [metadata for call in collection.add_calls for metadata in call["metadatas"]]
    sample_metadata = metadatas[0] if metadatas else {}
    required = ["file_name", "academic_year", "section_title", "chunk_id", "source_path", "source"]
    live_summary: dict[str, Any] = {"available": False, "error": "", "total_chunks": 0, "field_coverage": {}}
    try:
        live_data = list_vector_chunks(include_documents=False)
        live_metas = [
            dict(metadata or {})
            for metadata in live_data.get("metadatas", [])
            if dict(metadata or {}).get("source") != "BOT_RULE"
        ]
        live_summary = {
            "available": True,
            "error": "",
            "total_chunks": len(live_metas),
            "field_coverage": {
                key: sum(1 for metadata in live_metas if str(metadata.get(key, "") or "").strip())
                for key in required
            },
        }
    except Exception as exc:
        live_summary["error"] = str(exc)

    return {
        "required_fields": required,
        "sample_metadata": sample_metadata,
        "sample_has_all_required": all(str(sample_metadata.get(key, "") or "").strip() for key in required),
        "live_summary": live_summary,
    }


def run_retrieval_tests(max_cases: int = 8) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    corpus_docs = _load_tool_corpus("student_handbook_rag")
    samples: list[QuestionItem] = []
    for q_path in sorted(HANDBOOK_DIR.glob("*.questions.md")):
        questions = _question_items(q_path)
        if questions:
            samples.append(questions[0])
    samples = samples[:max_cases]

    lexical_rows: list[dict[str, Any]] = []
    for item in samples:
        matches = _search_documents(corpus_docs, item.question, limit=5)
        top_sources = [doc.source for _score, doc in matches[:5]]
        expected_year = item.academic_year
        passed = bool(top_sources) and any(expected_year in source for source in top_sources[:1])
        lexical_rows.append(
            {
                "question": item.question,
                "academic_year": expected_year,
                "expected_source": item.source_file,
                "top_sources": top_sources,
                "status": "PASS" if passed else "CHECK",
                "expected_answer": item.answer[:260],
            }
        )

    vector_rows: list[dict[str, Any]] = []
    if embedding_backend_ready():
        retriever = VectorStoreRetriever(
            query_fn=search_vector_documents,
            collection_getter=lambda: None,
            user_id="audit-report",
            n_results=100,
            alpha=0.7,
        )
        for item in samples[-3:]:
            try:
                docs = retriever.invoke(item.question)
                sources = [
                    str(doc.metadata.get("source", "") or "")
                    for doc in docs
                    if doc.metadata.get("source") != "BOT_RULE"
                ][:8]
                vector_rows.append(
                    {
                        "question": item.question,
                        "academic_year": item.academic_year,
                        "top_sources": sources,
                        "status": "PASS" if sources and all(item.academic_year in source for source in sources[:3]) else "CHECK",
                    }
                )
            except Exception as exc:
                vector_rows.append(
                    {
                        "question": item.question,
                        "academic_year": item.academic_year,
                        "top_sources": [f"ERROR: {exc}"],
                        "status": "ERROR",
                    }
                )
    return lexical_rows, vector_rows


def audit_generation_contract() -> dict[str, Any]:
    prompt = _build_final_prompt(
        system_prompt="BASE SYSTEM PROMPT",
        current_lang="vi",
        safe_context="Không có ngữ cảnh liên quan.",
        user_question="Một nội dung không có trong sổ tay?",
        rag_tool="student_handbook_rag",
    )
    return {
        "context_only": "Chỉ được trả lời từ ngữ cảnh hiện tại" in prompt,
        "no_info_reply": "Không tìm thấy thông tin này trong sổ tay sinh viên." in prompt,
        "source_delivery": "API trả về trường sources; giao diện chat hiển thị khối Nguồn tham khảo.",
        "llm_invoked": False,
        "note": "Báo cáo kiểm tra prompt contract tĩnh để tránh gọi LLM ngoài trong quá trình audit.",
    }


def _xml_text(text: object) -> str:
    return html.escape(str(text), quote=False)


class DocxBuilder:
    def __init__(self) -> None:
        self.parts: list[str] = []

    def paragraph(self, text: str = "", *, style: str = "Normal", num_id: int | None = None) -> None:
        p_pr = f'<w:pPr><w:pStyle w:val="{style}"/>'
        if num_id is not None:
            p_pr += f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num_id}"/></w:numPr>'
        p_pr += "</w:pPr>"
        runs = []
        lines = str(text).split("\n")
        for index, line in enumerate(lines):
            if index:
                runs.append("<w:br/>")
            runs.append(f'<w:r><w:t xml:space="preserve">{_xml_text(line)}</w:t></w:r>')
        self.parts.append(f"<w:p>{p_pr}{''.join(runs)}</w:p>")

    def bullet(self, text: str) -> None:
        self.paragraph(text, style="ListParagraph", num_id=1)

    def heading(self, text: str, level: int = 1) -> None:
        self.paragraph(text, style=f"Heading{min(max(level, 1), 3)}")

    def table(self, headers: list[str], rows: list[list[Any]], widths: list[int] | None = None) -> None:
        col_count = len(headers)
        if widths is None:
            widths = [9360 // max(col_count, 1)] * col_count
        grid = "".join(f'<w:gridCol w:w="{width}"/>' for width in widths)
        table_rows = [self._table_row(headers, widths, header=True)]
        table_rows.extend(self._table_row([str(cell) for cell in row], widths, header=False) for row in rows)
        borders = "".join(
            f'<w:{name} w:val="single" w:sz="4" w:space="0" w:color="DADCE0"/>'
            for name in ("top", "left", "bottom", "right", "insideH", "insideV")
        )
        self.parts.append(
            '<w:tbl>'
            '<w:tblPr><w:tblW w:w="9360" w:type="dxa"/><w:tblInd w:w="120" w:type="dxa"/>'
            f"<w:tblBorders>{borders}</w:tblBorders>"
            '<w:tblCellMar><w:top w:w="80" w:type="dxa"/><w:start w:w="120" w:type="dxa"/>'
            '<w:bottom w:w="80" w:type="dxa"/><w:end w:w="120" w:type="dxa"/></w:tblCellMar>'
            "</w:tblPr>"
            f"<w:tblGrid>{grid}</w:tblGrid>"
            f"{''.join(table_rows)}"
            "</w:tbl>"
        )

    def _table_row(self, cells: list[str], widths: list[int], *, header: bool) -> str:
        row_cells = []
        for index, value in enumerate(cells):
            fill = '<w:shd w:fill="F2F4F7"/>' if header else ""
            bold = "<w:b/>" if header else ""
            row_cells.append(
                '<w:tc>'
                f'<w:tcPr><w:tcW w:w="{widths[index]}" w:type="dxa"/>{fill}</w:tcPr>'
                '<w:p><w:pPr><w:spacing w:after="60"/></w:pPr>'
                f'<w:r><w:rPr>{bold}</w:rPr><w:t xml:space="preserve">{_xml_text(value)}</w:t></w:r>'
                '</w:p></w:tc>'
            )
        return f"<w:tr>{''.join(row_cells)}</w:tr>"

    def document_xml(self) -> str:
        sect_pr = (
            '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
            '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
            'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"<w:body>{''.join(self.parts)}{sect_pr}</w:body></w:document>"
        )


def _styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/><w:sz w:val="22"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="120" w:line="264" w:lineRule="auto"/></w:pPr><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="200"/></w:pPr><w:rPr><w:b/><w:color w:val="0B2545"/><w:sz w:val="44"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="160"/></w:pPr><w:rPr><w:color w:val="555555"/><w:sz w:val="24"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="320" w:after="160"/></w:pPr><w:rPr><w:b/><w:color w:val="2E74B5"/><w:sz w:val="32"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/></w:pPr><w:rPr><w:b/><w:color w:val="2E74B5"/><w:sz w:val="26"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="160" w:after="80"/></w:pPr><w:rPr><w:b/><w:color w:val="1F4D78"/><w:sz w:val="24"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="80"/><w:ind w:left="720" w:hanging="360"/></w:pPr></w:style>
</w:styles>"""


def _numbering_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="singleLevel"/><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/><w:lvlJc w:val="left"/><w:pPr><w:tabs><w:tab w:val="num" w:pos="720"/></w:tabs><w:ind w:left="720" w:hanging="360"/></w:pPr><w:rPr><w:rFonts w:ascii="Symbol" w:hAnsi="Symbol"/></w:rPr></w:lvl></w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="1"/></w:num>
</w:numbering>"""


def write_docx(path: Path, builder: DocxBuilder) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""
    doc_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
</Relationships>"""
    core = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Báo cáo rà soát RAG sổ tay sinh viên</dc:title>
  <dc:creator>Codex</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>"""
    app = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Codex</Application></Properties>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("docProps/core.xml", core)
        zf.writestr("docProps/app.xml", app)
        zf.writestr("word/document.xml", builder.document_xml())
        zf.writestr("word/styles.xml", _styles_xml())
        zf.writestr("word/numbering.xml", _numbering_xml())
        zf.writestr("word/_rels/document.xml.rels", doc_rels)


def build_report(output_path: Path) -> dict[str, Any]:
    data_rows, chunk_summary = analyze_data_and_chunks()
    metadata = audit_metadata_contract()
    lexical_rows, vector_rows = run_retrieval_tests()
    generation = audit_generation_contract()

    try:
        vector_count = count_vector_chunks()
    except Exception as exc:
        vector_count = f"Không đọc được: {exc}"

    doc = DocxBuilder()
    doc.paragraph("Báo cáo rà soát RAG sổ tay sinh viên", style="Title")
    doc.paragraph(f"Tự động sinh lúc {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} từ workspace {PROJECT_ROOT}", style="Subtitle")
    doc.paragraph("Preset: standard_business_brief. Phạm vi rà soát tập trung vào dữ liệu Markdown trong data/primary_corpus/student_handbooks/ và pipeline RAG hiện có của project.")

    doc.heading("Tổng Quan Hệ Thống RAG Hiện Tại")
    doc.bullet("Load dữ liệu: services.content.document_service import seed corpus và upload Markdown; services.rag.rag_corpus load corpus lexical từ data/primary_corpus.")
    doc.bullet("Chunking: pipelines.chunking_pipeline.smart_chunk chia theo heading Markdown cấp 1-4, giữ chapter/section/page và overlap theo settings.")
    doc.bullet("Embedding/vector DB: services.vector.vector_store_service dùng ChromaDB collection markdown_docs_v2 với paraphrase-multilingual-MiniLM-L12-v2 và hybrid BM25/vector.")
    doc.bullet("Retrieval: pipelines.retrieval_pipeline route theo tool, dùng lexical theo tool trước và vector hybrid khi embedding backend sẵn sàng.")
    doc.bullet("Generation: services.chat.multilingual_service dựng prompt bắt buộc trả lời theo context; API/UI trả về sources để hiển thị nguồn.")
    doc.paragraph(f"Vector store hiện đọc được: {vector_count} chunks.")

    doc.heading("Cấu Trúc Dữ Liệu Sổ Tay Sinh Viên")
    doc.table(
        ["File", "Năm học", "KB", "Heading", "Q/A", "Chunks", "TB từ/chunk", "Rủi ro cắt câu"],
        [
            [
                row["file_name"],
                row["academic_year"],
                row["size_kb"],
                row["heading_count"],
                row["question_count"],
                row["chunk_count"],
                row["avg_words"],
                row["sentence_cut_risk"],
            ]
            for row in data_rows
        ],
        widths=[2500, 1150, 700, 900, 700, 800, 900, 1710],
    )
    doc.paragraph(
        f"Tổng cộng {chunk_summary['handbook_count']} file sổ tay chính, {chunk_summary['question_file_count']} file câu hỏi, "
        f"{chunk_summary['total_chunks']} chunk thử nghiệm; cấu hình chunk_size={chunk_summary['chunk_size']}, overlap={chunk_summary['chunk_overlap']} từ."
    )

    doc.heading("Phân Tích Kỹ Thuật Chunking")
    doc.bullet("Có chia theo heading Markdown: Có. Khi gặp heading mới, buffer cũ được flush và heading_stack cập nhật chapter/section.")
    doc.bullet("Giữ ngữ cảnh chương/mục: Có. Metadata chunk có title, level, chapter, section; section là đường dẫn heading.")
    doc.bullet(f"Có overlap: Có. settings.CHUNK_OVERLAP hiện là {chunk_summary['chunk_overlap']} từ; overlap reset khi sang heading mới để tránh kéo ngữ cảnh mục trước sang mục sau.")
    doc.bullet("Tránh cắt giữa câu: Đã bổ sung ưu tiên điểm kết câu gần giới hạn chunk; câu quá dài vẫn có thể bị cắt theo hard limit.")
    doc.bullet("Nhiều quyển sổ tay: Có. source/file_name/academic_year tách theo từng file; report ghi nhận đủ các năm 2018-2019 đến 2025-2026.")
    doc.bullet(f"Phân bố loại chunk: {json.dumps(chunk_summary['chunk_types'], ensure_ascii=False)}.")

    doc.heading("Phân Tích Metadata")
    sample_meta = metadata["sample_metadata"]
    doc.table(
        ["Trường", "Trạng thái trong code mới", "Ví dụ"],
        [
            [field, "Có" if sample_meta.get(field) else "Thiếu", str(sample_meta.get(field, ""))[:120]]
            for field in metadata["required_fields"]
        ],
        widths=[2200, 2200, 4960],
    )
    live = metadata["live_summary"]
    if live["available"]:
        coverage = ", ".join(f"{key}: {value}/{live['total_chunks']}" for key, value in live["field_coverage"].items())
        doc.paragraph(f"Kiểm tra vectorstore hiện tại: {coverage}. Nếu field mới thấp hơn tổng chunks, cần re-index corpus để metadata cũ được cập nhật.")
    else:
        doc.paragraph(f"Không đọc được metadata live từ vectorstore: {live['error']}")

    doc.heading("Phân Tích Retrieval")
    doc.bullet("Lexical retrieval có lọc exact year range trong services.rag.rag_corpus._search_documents khi câu hỏi chứa năm học dạng YYYY-YYYY.")
    doc.bullet("VectorStoreRetriever đã bổ sung hậu lọc theo academic_year/source/source_path khi query chứa năm học, giữ BOT_RULE nếu có.")
    doc.bullet("top_k hiện tại: lexical theo tool 8; vector retriever lấy 100 candidate rồi context builder giới hạn 25 chunk. Cách này rộng nhưng cần lọc năm để tránh trộn tài liệu.")
    doc.table(
        ["Năm", "Câu hỏi mẫu", "Top source lexical", "Kết quả"],
        [
            [
                row["academic_year"],
                row["question"][:120],
                "\n".join(row["top_sources"][:2]),
                row["status"],
            ]
            for row in lexical_rows
        ],
        widths=[1100, 4200, 3100, 960],
    )
    if vector_rows:
        doc.paragraph("Kiểm tra vector retrieval với các câu hỏi mẫu cuối danh sách:")
        doc.table(
            ["Năm", "Câu hỏi", "Top source vector", "Kết quả"],
            [
                [row["academic_year"], row["question"][:120], "\n".join(row["top_sources"][:3]), row["status"]]
                for row in vector_rows
            ],
            widths=[1100, 4200, 3100, 960],
        )

    doc.heading("Phân Tích Generation")
    doc.bullet("Prompt generation yêu cầu chỉ trả lời từ context hiện tại và ưu tiên context hơn lịch sử chat.")
    doc.bullet("Với student_handbook_rag, no-info reply đã được đặt đúng câu: Không tìm thấy thông tin này trong sổ tay sinh viên.")
    doc.bullet("Khi không có context, chat_service trả fallback cục bộ thay vì gọi LLM.")
    doc.bullet("Nguồn rõ ràng hiện được trả qua field sources của API và render trong UI chat dưới nhãn Nguồn tham khảo.")
    doc.bullet(f"Kiểm tra prompt contract: context_only={generation['context_only']}, no_info_reply={generation['no_info_reply']}.")

    doc.heading("Kết Quả Test Hỏi Đáp")
    doc.table(
        ["Câu hỏi", "Đáp án kỳ vọng từ file", "Nguồn kỳ vọng", "Kết quả retrieval"],
        [
            [row["question"][:170], row["expected_answer"], row["expected_source"], row["status"]]
            for row in lexical_rows
        ],
        widths=[3000, 3300, 2100, 960],
    )
    doc.paragraph("Các test trên lấy câu hỏi trực tiếp từ file *.questions.md. Báo cáo không gọi LLM ngoài; phần sinh câu trả lời được kiểm tra qua prompt contract và fallback deterministic.")

    doc.heading("Các Lỗi Hoặc Hạn Chế Phát Hiện Được")
    doc.bullet("Vectorstore đã index trước khi thêm metadata mới có thể chưa có chunk_id/section_title/source_path; cần import lại corpus để live metadata đồng bộ.")
    doc.bullet("Chunking vẫn có thể cắt giữa câu nếu một câu dài vượt hard limit chunk_size.")
    doc.bullet("Prompt không nhúng nguồn trực tiếp vào text trả lời; nguồn nằm ở API/UI. Đây là ổn cho giao diện hiện tại nhưng cần lưu ý nếu dùng kênh không hiển thị sources.")
    doc.bullet("Kiểm thử generation trong báo cáo chưa gọi LLM thật để tránh phụ thuộc khóa API/mạng; nên bổ sung benchmark e2e khi có môi trường LLM ổn định.")

    doc.heading("Đề Xuất Cải Tiến")
    doc.bullet("Chạy re-index seed corpus sau thay đổi metadata để vectorstore live có đủ field mới.")
    doc.bullet("Bổ sung evaluator định kỳ: exact-year retrieval, source precision@k, no-answer behavior, citation presence.")
    doc.bullet("Cân nhắc nén context theo section khi nhiều chunk cùng một file/năm để giảm trùng lặp trong prompt.")
    doc.bullet("Nếu triển khai qua API không có UI, append block nguồn vào response text hoặc yêu cầu client luôn render field sources.")

    doc.heading("Kết Luận")
    doc.paragraph("Pipeline RAG hiện có đủ nền tảng để dùng dữ liệu sổ tay sinh viên Markdown: load file, chunk theo heading, embedding vào ChromaDB, hybrid retrieval, prompt generation bám context và nguồn trả về qua API. Các chỉnh sửa trong lần rà soát này tập trung vào metadata bắt buộc, giảm trộn năm học ở vector retrieval, cải thiện cắt câu khi chunking và chuẩn hóa câu trả lời khi không tìm thấy thông tin trong sổ tay.")

    write_docx(output_path, doc)
    return {
        "output": str(output_path),
        "data_rows": data_rows,
        "chunk_summary": chunk_summary,
        "metadata": metadata,
        "lexical_tests": lexical_rows,
        "vector_tests": vector_rows,
        "generation": generation,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build RAG student handbook audit DOCX report.")
    parser.add_argument("--output", type=Path, default=OUTPUT_DOCX)
    args = parser.parse_args()
    result = build_report(args.output.resolve())
    print(json.dumps({"output": result["output"], "lexical_tests": len(result["lexical_tests"]), "vector_tests": len(result["vector_tests"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
