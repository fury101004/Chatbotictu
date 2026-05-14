from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


def _find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "main.py").exists() and (parent / "services").is_dir():
            return parent
    return Path(__file__).resolve().parents[2]


ROOT = _find_repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.rag_tools import (  # noqa: E402
    DEFAULT_RAG_TOOL,
    FALLBACK_RAG_NODE,
    build_upload_source_name,
    get_tool_upload_dir,
)
from repositories.upload_repository import record_uploaded_file  # noqa: E402
from repositories.vector_repository import delete_vector_source, get_vector_collection  # noqa: E402
from services.content.web_search import web_search_configured  # noqa: E402
from services.rag.rag_corpus import clear_rag_corpus_cache  # noqa: E402
from services.rag.rag_service import (  # noqa: E402
    _fallback_retrieval_flow,
    _route_rag_tool_by_keyword,
    retrieve_fallback_context,
    retrieve_tool_context,
    route_rag_tool,
    route_retrieval_flow,
)
from services.rag.rag_types import RETRIEVAL_WEB_FIRST, RETRIEVAL_WEB_SEARCH  # noqa: E402
from services.vector.vector_store_service import add_documents, embedding_backend_ready  # noqa: E402


DEFAULT_DATASET = ROOT / "docs" / "evaluation" / "ictu_30_questions_dataset.json"
DEFAULT_OUTPUT_JSON = ROOT / "docs" / "evaluation" / "ictu_30_questions_results.json"
DEFAULT_OUTPUT_MD = ROOT / "docs" / "evaluation" / "ictu_30_questions_results.md"
DEFAULT_KB_FILE = get_tool_upload_dir(DEFAULT_RAG_TOOL) / "ictu-30-question-evaluation-knowledge-base.md"


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text or "").casefold())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    compact = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in stripped)
    return " ".join(compact.split())


def _compact(text: str, limit: int = 420) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + " ..."


def _first_match_rank(sources: list[str], expected_parts: list[str]) -> int | None:
    normalized_expected = [_normalize(part) for part in expected_parts if part]
    if not normalized_expected:
        return None

    for index, source in enumerate(sources, start=1):
        normalized_source = _normalize(source)
        if any(part in normalized_source for part in normalized_expected):
            return index
    return None


def _tool_matches(expected_tool: str, predicted_tool: str) -> bool:
    expected = str(expected_tool or "any").strip()
    return expected in {"", "any", "*"} or predicted_tool == expected


def _flow_matches(expected_flow: str, plan_source: str, plan_priority: str, retrieval_mode: str) -> bool:
    expected = str(expected_flow or "local_data").strip()
    mode = str(retrieval_mode or "")
    if expected == RETRIEVAL_WEB_SEARCH:
        return (
            plan_source == RETRIEVAL_WEB_SEARCH
            or plan_priority == RETRIEVAL_WEB_FIRST
            or "web_search" in mode
            or "web_knowledge" in mode
        )
    return plan_source != RETRIEVAL_WEB_SEARCH and plan_priority != RETRIEVAL_WEB_FIRST


def _retrieve(question: str, session_id: str, predicted_tool: str, route_name: str, plan):
    if predicted_tool == FALLBACK_RAG_NODE:
        return retrieve_fallback_context(
            question,
            session_id=session_id,
            route_name=route_name,
            retrieval_plan=plan,
        )
    return retrieve_tool_context(
        message=question,
        session_id=session_id,
        tool_name=predicted_tool,
        route_name=route_name,
        retrieval_plan=plan,
    )


def evaluate_case(case: dict[str, Any], *, use_llm_router: bool = False, live_web: bool = False) -> dict[str, Any]:
    question = str(case["question"])
    expected_tool = str(case.get("expected_tool") or "any")
    expected_flow = str(case.get("expected_flow") or "local_data")
    expected_sources = list(case.get("expected_source_contains") or [])
    group = str(case.get("group") or expected_flow)

    started_at = time.perf_counter()
    if use_llm_router:
        predicted_tool, route_name = route_rag_tool(question)
    else:
        predicted_tool, route_name = _route_rag_tool_by_keyword(question)

    plan_tool = None if predicted_tool == FALLBACK_RAG_NODE else predicted_tool
    plan = route_retrieval_flow(question, plan_tool) if use_llm_router else _fallback_retrieval_flow(question)

    if expected_flow == RETRIEVAL_WEB_SEARCH and not live_web:
        retrieval_sources: list[str] = []
        retrieval_chunks_used = 0
        retrieval_mode = "web_search_plan_only"
        context_excerpt = (
            "Đã chọn luồng web_search theo realtime marker; không gọi live web trong lần chạy này."
        )
    else:
        retrieval = _retrieve(
            question,
            session_id=f"eval_ictu_30_{case['id']}",
            predicted_tool=predicted_tool,
            route_name=route_name,
            plan=plan,
        )
        retrieval_sources = retrieval.sources
        retrieval_chunks_used = retrieval.chunks_used
        retrieval_mode = retrieval.mode
        context_excerpt = _compact(retrieval.context_text)
    latency_ms = round((time.perf_counter() - started_at) * 1000, 2)

    source_rank = _first_match_rank(retrieval_sources, expected_sources)
    has_source_expectation = bool(expected_sources)
    source_hit = source_rank is not None if has_source_expectation else None
    tool_match = _tool_matches(expected_tool, predicted_tool)
    flow_match = _flow_matches(expected_flow, plan.source, plan.priority, retrieval_mode)
    passed = tool_match and flow_match and (source_hit is not False)

    return {
        "id": case["id"],
        "group": group,
        "question": question,
        "expected_tool": expected_tool,
        "predicted_tool": predicted_tool,
        "tool_match": tool_match,
        "route_name": route_name,
        "expected_flow": expected_flow,
        "flow_source": plan.source,
        "flow_priority": plan.priority,
        "flow_route": plan.route,
        "flow_reason": plan.reason,
        "flow_confidence": plan.confidence,
        "flow_match": flow_match,
        "expected_source_contains": expected_sources,
        "source_match_rank": source_rank,
        "source_hit": source_hit,
        "sources": retrieval_sources,
        "chunks_used": retrieval_chunks_used,
        "mode": retrieval_mode,
        "context_excerpt": context_excerpt,
        "latency_ms": latency_ms,
        "passed": passed,
    }


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _summarize(
    cases: list[dict[str, Any]],
    dataset_path: Path,
    *,
    use_llm_router: bool,
    live_web: bool,
) -> dict[str, Any]:
    route_labeled = [case for case in cases if case["expected_tool"] not in {"", "any", "*"}]
    source_labeled = [case for case in cases if case["expected_source_contains"]]
    local_cases = [case for case in cases if case["group"] == "local_data"]
    web_cases = [case for case in cases if case["group"] == "web_search"]
    latency_values = [case["latency_ms"] for case in cases]
    chunk_values = [case["chunks_used"] for case in cases]

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "dataset_path": str(dataset_path),
        "total_cases": len(cases),
        "local_data_cases": len(local_cases),
        "web_search_cases": len(web_cases),
        "overall_accuracy": _rate(sum(1 for case in cases if case["passed"]), len(cases)),
        "local_accuracy": _rate(sum(1 for case in local_cases if case["passed"]), len(local_cases)),
        "web_flow_accuracy": _rate(sum(1 for case in web_cases if case["flow_match"]), len(web_cases)),
        "route_accuracy": _rate(sum(1 for case in route_labeled if case["tool_match"]), len(route_labeled)),
        "flow_accuracy": _rate(sum(1 for case in cases if case["flow_match"]), len(cases)),
        "source_hit_rate": _rate(
            sum(1 for case in source_labeled if case["source_hit"]),
            len(source_labeled),
        ),
        "source_top1_hit_rate": _rate(
            sum(1 for case in source_labeled if case["source_match_rank"] == 1),
            len(source_labeled),
        ),
        "avg_latency_ms": round(statistics.fmean(latency_values), 2) if latency_values else 0,
        "min_latency_ms": min(latency_values) if latency_values else 0,
        "max_latency_ms": max(latency_values) if latency_values else 0,
        "avg_chunks_used": round(statistics.fmean(chunk_values), 2) if chunk_values else 0,
        "web_search_configured": web_search_configured(),
        "use_llm_router": use_llm_router,
        "live_web_enabled": live_web,
        "embedding_backend_ready": embedding_backend_ready(),
        "vectorstore_chunks": get_vector_collection().count(),
        "group_distribution": dict(Counter(case["group"] for case in cases)),
        "predicted_tool_distribution": dict(Counter(case["predicted_tool"] for case in cases)),
        "flow_source_distribution": dict(Counter(case["flow_source"] for case in cases)),
        "failing_cases": [case for case in cases if not case["passed"]],
        "cases": cases,
    }


def evaluate_dataset(dataset_path: Path, *, use_llm_router: bool = False, live_web: bool = False) -> dict[str, Any]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = [
        evaluate_case(item, use_llm_router=use_llm_router, live_web=live_web)
        for item in dataset
    ]
    return _summarize(cases, dataset_path, use_llm_router=use_llm_router, live_web=live_web)


def _yes_no(value: object) -> str:
    if value is None:
        return "-"
    return "yes" if bool(value) else "no"


def build_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Báo cáo kiểm thử 30 câu hỏi ICTU",
        "",
        f"- Thời gian chạy: {report['generated_at']}",
        f"- Tổng số câu: {report['total_cases']}",
        f"- Nhóm dữ liệu nội bộ: {report['local_data_cases']}",
        f"- Nhóm luồng web search: {report['web_search_cases']}",
        f"- Overall accuracy: {report['overall_accuracy']:.2%}",
        f"- Local accuracy: {report['local_accuracy']:.2%}",
        f"- Web-flow accuracy: {report['web_flow_accuracy']:.2%}",
        f"- Route accuracy: {report['route_accuracy']:.2%}",
        f"- Flow accuracy: {report['flow_accuracy']:.2%}",
        f"- Source hit rate: {report['source_hit_rate']:.2%}",
        f"- Source top-1 hit rate: {report['source_top1_hit_rate']:.2%}",
        f"- Độ trễ trung bình: {report['avg_latency_ms']} ms",
        f"- Số chunk trung bình: {report['avg_chunks_used']}",
        f"- Web search configured: {report['web_search_configured']}",
        f"- Live web enabled: {report['live_web_enabled']}",
        f"- Use LLM router: {report['use_llm_router']}",
        f"- Embedding backend ready: {report['embedding_backend_ready']}",
        "",
        "## Kết quả từng câu",
        "",
        "| id | nhóm | route | flow | source | pass | latency ms | nguồn đầu tiên |",
        "| --- | --- | --- | --- | --- | --- | ---: | --- |",
    ]

    for case in report["cases"]:
        first_source = case["sources"][0] if case["sources"] else "-"
        lines.append(
            f"| {case['id']} | {case['group']} | {_yes_no(case['tool_match'])} | "
            f"{_yes_no(case['flow_match'])} | {_yes_no(case['source_hit'])} | "
            f"{_yes_no(case['passed'])} | {case['latency_ms']} | {first_source} |"
        )

    if report["failing_cases"]:
        lines.extend(["", "## Ca cần xem lại"])
        for case in report["failing_cases"]:
            lines.append(
                f"- {case['id']}: predicted_tool={case['predicted_tool']}, "
                f"flow={case['flow_source']}/{case['flow_priority']}, "
                f"source_hit={case['source_hit']}"
            )

    return "\n".join(lines) + "\n"


def build_knowledge_base_markdown(report: dict[str, Any]) -> str:
    lines = [
        "---",
        'title: "ICTU 30-question evaluation knowledge base"',
        f'generated_at: "{report["generated_at"]}"',
        'source_type: "evaluation"',
        'tool_name: "student_faq_rag"',
        'generator: "tools/evaluation/evaluate_ictu_30_questions.py"',
        "---",
        "",
        "# ICTU 30-question evaluation knowledge base",
        "",
        "## Tóm tắt",
        "",
        f"- Tổng số câu kiểm thử: {report['total_cases']}.",
        f"- 15 câu kiểm dữ liệu nội bộ, 15 câu kiểm luồng web search.",
        f"- Overall accuracy: {report['overall_accuracy']:.2%}.",
        f"- Route accuracy: {report['route_accuracy']:.2%}.",
        f"- Flow accuracy: {report['flow_accuracy']:.2%}.",
        f"- Source hit rate: {report['source_hit_rate']:.2%}.",
        f"- Web search configured khi chạy: {report['web_search_configured']}.",
        f"- Live web enabled khi chạy: {report['live_web_enabled']}.",
        f"- Use LLM router khi chạy: {report['use_llm_router']}.",
        "",
        "## Bộ câu hỏi và kết quả",
        "",
    ]

    for case in report["cases"]:
        sources = ", ".join(case["sources"][:3]) if case["sources"] else "Không có nguồn trả về"
        lines.extend(
            [
                f"### {case['id']} - {case['group']}",
                "",
                f"**Câu hỏi:** {case['question']}",
                "",
                f"**Kết quả:** {'Đạt' if case['passed'] else 'Cần xem lại'}",
                "",
                f"- Expected tool: `{case['expected_tool']}`",
                f"- Predicted tool: `{case['predicted_tool']}`",
                f"- Expected flow: `{case['expected_flow']}`",
                f"- Predicted flow: `{case['flow_source']}` / `{case['flow_priority']}`",
                f"- Retrieval mode: `{case['mode']}`",
                f"- Chunks used: `{case['chunks_used']}`",
                f"- Sources: {sources}",
                "",
                "**Trích ngữ cảnh truy xuất:**",
                "",
                case["context_excerpt"] or "Không có ngữ cảnh truy xuất.",
                "",
            ]
        )

    return "\n".join(lines)


def save_knowledge_base_file(markdown: str, kb_path: Path) -> dict[str, Any]:
    kb_path.parent.mkdir(parents=True, exist_ok=True)
    kb_path.write_text(markdown, encoding="utf-8")

    tool_name = DEFAULT_RAG_TOOL
    filename = kb_path.name
    source_name = build_upload_source_name(tool_name, filename)
    indexed = False
    warning = ""

    try:
        delete_vector_source(source_name)
    except Exception:
        pass

    record_uploaded_file(filename=filename, tool_name=tool_name, storage_path=source_name)

    if embedding_backend_ready():
        try:
            add_documents(
                file_content=markdown,
                filename=filename,
                source_name=source_name,
                tool_name=tool_name,
            )
            indexed = True
        except Exception as exc:
            warning = f"Không index được Knowledge Base vào vector store: {exc}"
    else:
        warning = "Embedding backend chưa sẵn sàng; đã lưu file nhưng chưa index vector store."

    clear_rag_corpus_cache()
    return {
        "path": str(kb_path),
        "source_name": source_name,
        "indexed": indexed,
        "warning": warning,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the 30 ICTU local/web-search benchmark questions.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--kb-file", type=Path, default=DEFAULT_KB_FILE)
    parser.add_argument(
        "--use-llm-router",
        action="store_true",
        help="Use LLM router/flow planner. Default is deterministic keyword + fallback flow.",
    )
    parser.add_argument(
        "--live-web",
        action="store_true",
        help="Call the configured live web search backend for web_search cases.",
    )
    args = parser.parse_args()

    try:
        delete_vector_source(build_upload_source_name(DEFAULT_RAG_TOOL, args.kb_file.name))
        args.kb_file.unlink(missing_ok=True)
        clear_rag_corpus_cache()
    except Exception:
        pass

    report = evaluate_dataset(args.dataset, use_llm_router=args.use_llm_router, live_web=args.live_web)
    markdown_report = build_markdown_report(report)
    kb_markdown = build_knowledge_base_markdown(report)
    kb_status = save_knowledge_base_file(kb_markdown, args.kb_file)
    report["knowledge_base"] = kb_status

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output_md.write_text(markdown_report, encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "ok",
                "total_cases": report["total_cases"],
                "overall_accuracy": report["overall_accuracy"],
                "local_accuracy": report["local_accuracy"],
                "web_flow_accuracy": report["web_flow_accuracy"],
                "route_accuracy": report["route_accuracy"],
                "flow_accuracy": report["flow_accuracy"],
                "source_hit_rate": report["source_hit_rate"],
                "knowledge_base": kb_status,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
