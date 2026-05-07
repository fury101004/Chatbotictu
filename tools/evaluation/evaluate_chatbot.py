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

from config.rag_tools import FALLBACK_RAG_NODE  # noqa: E402
from services.llm.llm_service import get_model  # noqa: E402
from services.rag.rag_service import (  # noqa: E402
    retrieve_fallback_context,
    retrieve_tool_context,
    route_rag_tool,
)
from services.vector.vector_store_service import get_collection  # noqa: E402


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    compact = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in stripped)
    return " ".join(compact.split())


def _first_match_rank(sources: list[str], expected_parts: list[str]) -> int | None:
    if not expected_parts:
        return None

    normalized_expected = [_normalize(part) for part in expected_parts if part]
    for index, source in enumerate(sources, start=1):
        normalized_source = _normalize(source)
        if any(part in normalized_source for part in normalized_expected):
            return index
    return None


def _warm_up_runtime() -> None:
    get_collection().count()
    route_rag_tool("warmup handbook")
    retrieve_tool_context(
        message="So tay sinh vien khoa 24",
        session_id="eval_warmup_handbook",
        tool_name="student_handbook_rag",
        route_name="warmup_handbook",
    )
    retrieve_tool_context(
        message="Thong tu 08 nam 2021",
        session_id="eval_warmup_policy",
        tool_name="school_policy_rag",
        route_name="warmup_policy",
    )
    retrieve_tool_context(
        message="Ke hoach xet tot nghiep 2026",
        session_id="eval_warmup_faq",
        tool_name="student_faq_rag",
        route_name="warmup_faq",
    )
    retrieve_fallback_context(
        "Thong tin cho sinh vien khoa 24",
        session_id="eval_warmup_fallback",
        route_name="warmup_fallback",
    )


def _evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    question = str(case["question"])
    expected_tool = str(case["expected_tool"])
    expected_sources = list(case.get("expected_source_contains", []))

    started_at = time.perf_counter()
    predicted_tool, route_name = route_rag_tool(question)
    if predicted_tool == FALLBACK_RAG_NODE:
        retrieval = retrieve_fallback_context(question, session_id=f"eval_{case['id']}", route_name=route_name)
    else:
        retrieval = retrieve_tool_context(
            message=question,
            session_id=f"eval_{case['id']}",
            tool_name=predicted_tool,
            route_name=route_name,
        )
    latency_ms = round((time.perf_counter() - started_at) * 1000, 2)

    sources = retrieval.sources
    source_rank = _first_match_rank(sources, expected_sources)

    return {
        "id": case["id"],
        "question": question,
        "expected_tool": expected_tool,
        "predicted_tool": predicted_tool,
        "tool_match": predicted_tool == expected_tool,
        "route_name": route_name,
        "expected_source_contains": expected_sources,
        "source_match_rank": source_rank,
        "source_hit": source_rank is not None,
        "sources": sources,
        "chunks_used": retrieval.chunks_used,
        "mode": retrieval.mode,
        "latency_ms": latency_ms,
    }


def evaluate_dataset(dataset_path: Path) -> dict[str, Any]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    _warm_up_runtime()
    cases = [_evaluate_case(item) for item in dataset]
    labeled_source_cases = [case for case in cases if case["expected_source_contains"]]

    route_correct = sum(1 for case in cases if case["tool_match"])
    source_hits = sum(1 for case in labeled_source_cases if case["source_hit"])
    source_top1 = sum(1 for case in labeled_source_cases if case["source_match_rank"] == 1)
    reciprocal_ranks = [
        1 / case["source_match_rank"]
        for case in labeled_source_cases
        if case["source_match_rank"] is not None
    ]

    route_prefix_distribution = Counter(
        case["route_name"].split(":", 1)[0] if case["route_name"] else "unknown"
        for case in cases
    )
    predicted_tool_distribution = Counter(case["predicted_tool"] for case in cases)
    expected_tool_distribution = Counter(case["expected_tool"] for case in cases)
    latency_values = [case["latency_ms"] for case in cases]
    chunk_values = [case["chunks_used"] for case in cases]

    failing_cases = [
        case
        for case in cases
        if not case["tool_match"] or (case["expected_source_contains"] and not case["source_hit"])
    ]

    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "dataset_path": str(dataset_path),
        "total_cases": len(cases),
        "labeled_source_cases": len(labeled_source_cases),
        "route_accuracy": round(route_correct / len(cases), 4) if cases else 0,
        "source_hit_rate": round(source_hits / len(labeled_source_cases), 4) if labeled_source_cases else 0,
        "source_top1_hit_rate": round(source_top1 / len(labeled_source_cases), 4) if labeled_source_cases else 0,
        "source_mrr": round(statistics.fmean(reciprocal_ranks), 4) if reciprocal_ranks else 0,
        "avg_latency_ms": round(statistics.fmean(latency_values), 2) if latency_values else 0,
        "min_latency_ms": min(latency_values) if latency_values else 0,
        "max_latency_ms": max(latency_values) if latency_values else 0,
        "avg_chunks_used": round(statistics.fmean(chunk_values), 2) if chunk_values else 0,
        "expected_tool_distribution": dict(sorted(expected_tool_distribution.items())),
        "predicted_tool_distribution": dict(sorted(predicted_tool_distribution.items())),
        "route_prefix_distribution": dict(sorted(route_prefix_distribution.items())),
        "vectorstore_chunks": get_collection().count(),
        "generation_model_configured": get_model() is not None,
        "cases": cases,
        "failing_cases": failing_cases,
    }


def build_markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        "# Tom tat benchmark chatbot",
        "",
        f"- Tong so ca kiem thu: {report['total_cases']}",
        f"- So ca co nhan nguon: {report['labeled_source_cases']}",
        f"- Do chinh xac dinh tuyen: {report['route_accuracy']:.2%}",
        f"- Ty le tim dung nguon: {report['source_hit_rate']:.2%}",
        f"- Ty le dung nguon top-1: {report['source_top1_hit_rate']:.2%}",
        f"- MRR nguon: {report['source_mrr']}",
        f"- Do tre trung binh: {report['avg_latency_ms']} ms",
        f"- So chunk trung binh: {report['avg_chunks_used']}",
        f"- Model sinh phan hoi da duoc cau hinh: {report['generation_model_configured']}",
        "",
        "## Phan bo route",
    ]

    for key, value in report["route_prefix_distribution"].items():
        lines.append(f"- {key}: {value}")

    lines.extend(
        [
            "",
            "## Ket qua tung ca",
            "",
            "| id | tool ky vong | tool du doan | match tool | match source | latency ms | nguon dau tien |",
            "| --- | --- | --- | --- | --- | ---: | --- |",
        ]
    )

    for case in report["cases"]:
        first_source = case["sources"][0] if case["sources"] else "-"
        lines.append(
            f"| {case['id']} | {case['expected_tool']} | {case['predicted_tool']} | "
            f"{'yes' if case['tool_match'] else 'no'} | "
            f"{'yes' if case['source_hit'] else ('-' if not case['expected_source_contains'] else 'no')} | "
            f"{case['latency_ms']} | {first_source} |"
        )

    if report["failing_cases"]:
        lines.extend(
            [
                "",
                "## Ca can chu y",
            ]
        )
        for case in report["failing_cases"]:
            lines.append(
                f"- {case['id']}: expected_tool={case['expected_tool']}, "
                f"predicted_tool={case['predicted_tool']}, "
                f"source_hit={case['source_hit']}"
            )

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Danh gia router va truy hoi cua chatbot.")
    parser.add_argument(
        "--dataset",
        default=str(ROOT / "evaluation" / "chatbot_eval_dataset.json"),
        help="File JSON chua bo test danh gia.",
    )
    parser.add_argument(
        "--output-json",
        default=str(ROOT / "reports" / "generated" / "eval_results.json"),
        help="File JSON ket qua benchmark.",
    )
    parser.add_argument(
        "--output-md",
        default=str(ROOT / "reports" / "generated" / "eval_results.md"),
        help="File Markdown tom tat benchmark.",
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)

    report = evaluate_dataset(dataset_path)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    output_md.write_text(build_markdown_summary(report), encoding="utf-8")

    print(json.dumps({
        "status": "ok",
        "total_cases": report["total_cases"],
        "route_accuracy": report["route_accuracy"],
        "source_hit_rate": report["source_hit_rate"],
        "output_json": str(output_json),
        "output_md": str(output_md),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

