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
    _fallback_retrieval_flow,
    _route_rag_tool_by_keyword,
    retrieve_fallback_context,
    retrieve_tool_context,
    route_rag_tool,
)


DATASET_PATH = ROOT / "docs" / "evaluation" / "ictu_30_questions_dataset.json"
OUTPUT_JSON = ROOT / "docs" / "evaluation" / "current_benchmark_results.json"
OUTPUT_MD = ROOT / "docs" / "evaluation" / "current_benchmark_results.md"


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or "").casefold())
    stripped = "".join(char for char in normalized if not unicodedata.combining(char))
    compact = "".join(char if char.isalnum() or char.isspace() else " " for char in stripped)
    return " ".join(compact.split())


def _source_rank(sources: list[str], expected_parts: list[str]) -> int | None:
    normalized_expected = [_normalize(part) for part in expected_parts if str(part).strip()]
    for rank, source in enumerate(sources, start=1):
        normalized_source = _normalize(source)
        if any(part in normalized_source for part in normalized_expected):
            return rank
    return None


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * percentile)))
    return round(float(ordered[index]), 2)


def _router_mode(route_name: str) -> str:
    if route_name.startswith("router_llm"):
        return "llm"
    if route_name.startswith("router_keyword"):
        return "keyword"
    if "fallback" in route_name:
        return "fallback"
    return "controlled"


def _failure_reasons(*, tool_match: bool, expected_sources: list[str], source_rank: int | None) -> list[str]:
    reasons: list[str] = []
    if not tool_match:
        reasons.append("selected_tool_mismatch")
    if expected_sources and source_rank is None:
        reasons.append("expected_source_not_in_retrieved_ranking")
    return reasons


def evaluate_case(case: dict[str, Any], *, router_mode: str) -> dict[str, Any]:
    question = str(case["question"])
    expected_tool = str(case.get("expected_tool") or "")
    expected_sources = [str(value) for value in case.get("expected_source_contains", [])]

    started_at = time.perf_counter()
    if router_mode == "keyword":
        selected_tool, route_name = _route_rag_tool_by_keyword(question)
        retrieval_plan = _fallback_retrieval_flow(question, route="benchmark_keyword_flow")
    else:
        selected_tool, route_name = route_rag_tool(question)
        retrieval_plan = None

    if selected_tool == FALLBACK_RAG_NODE:
        retrieval = retrieve_fallback_context(
            question,
            session_id=f"benchmark_{case['id']}",
            route_name=route_name,
            retrieval_plan=retrieval_plan,
        )
    else:
        retrieval = retrieve_tool_context(
            message=question,
            session_id=f"benchmark_{case['id']}",
            tool_name=selected_tool,
            route_name=route_name,
            retrieval_plan=retrieval_plan,
        )
    latency_ms = round((time.perf_counter() - started_at) * 1000, 2)

    sources = list(retrieval.sources)
    source_rank = _source_rank(sources, expected_sources)
    tool_match = not expected_tool or expected_tool in {"any", "*"} or selected_tool == expected_tool
    failure_reasons = _failure_reasons(
        tool_match=tool_match,
        expected_sources=expected_sources,
        source_rank=source_rank,
    )
    return {
        "id": str(case["id"]),
        "group": str(case.get("group") or ""),
        "question": question,
        "expected_tool": expected_tool,
        "selected_tool": selected_tool,
        "tool_match": tool_match,
        "route_name": route_name,
        "router_mode": _router_mode(route_name),
        "expected_source_contains": expected_sources,
        "source_rank": source_rank,
        "source_top1": source_rank == 1,
        "source_top3": source_rank is not None and source_rank <= 3,
        "reciprocal_rank": round(1 / source_rank, 6) if source_rank else 0.0,
        "sources": sources,
        "fallback_used": selected_tool == FALLBACK_RAG_NODE or "fallback" in route_name,
        "retrieval_mode": retrieval.mode,
        "fusion_method": retrieval.fusion_method,
        "routing_reason": retrieval.routing_reason,
        "confidence": retrieval.confidence,
        "fallback_reason": retrieval.fallback_reason,
        "latency_ms": latency_ms,
        "passed": not failure_reasons,
        "failure_reasons": failure_reasons,
    }


def evaluate_dataset(*, router_mode: str = "controlled") -> dict[str, Any]:
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    dataset_sha256 = __import__("hashlib").sha256(DATASET_PATH.read_bytes()).hexdigest()
    cases: list[dict[str, Any]] = []
    for index, case in enumerate(dataset, start=1):
        result = evaluate_case(case, router_mode=router_mode)
        cases.append(result)
        print(
            f"[{index}/{len(dataset)}] {result['id']}: "
            f"tool={result['selected_tool']} source_rank={result['source_rank']} "
            f"latency_ms={result['latency_ms']}",
            file=sys.stderr,
            flush=True,
        )
    source_cases = [case for case in cases if case["expected_source_contains"]]
    latencies = [float(case["latency_ms"]) for case in cases]

    route_correct = sum(1 for case in cases if case["tool_match"])
    top1 = sum(1 for case in source_cases if case["source_top1"])
    top3 = sum(1 for case in source_cases if case["source_top3"])
    reciprocal_ranks = [float(case["reciprocal_rank"]) for case in source_cases]
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "dataset_path": DATASET_PATH.relative_to(ROOT).as_posix(),
        "dataset_sha256": dataset_sha256,
        "router_mode_requested": router_mode,
        "router_mode_distribution": dict(Counter(case["router_mode"] for case in cases)),
        "total_cases": len(cases),
        "route_accuracy": round(route_correct / len(cases), 6) if cases else 0.0,
        "source_top1": round(top1 / len(source_cases), 6) if source_cases else 0.0,
        "source_top3": round(top3 / len(source_cases), 6) if source_cases else 0.0,
        "mrr": round(statistics.fmean(reciprocal_ranks), 6) if reciprocal_ranks else 0.0,
        "fallback_count": sum(1 for case in cases if case["fallback_used"]),
        "latency_ms": {
            "min": round(min(latencies), 2) if latencies else 0.0,
            "max": round(max(latencies), 2) if latencies else 0.0,
            "mean": round(statistics.fmean(latencies), 2) if latencies else 0.0,
            "median": round(statistics.median(latencies), 2) if latencies else 0.0,
            "p95": _percentile(latencies, 0.95),
        },
        "selected_tool_distribution": dict(Counter(case["selected_tool"] for case in cases)),
        "model_configured": get_model() is not None,
        "wrong_cases": [case for case in cases if not case["passed"]],
        "cases": cases,
    }


def build_markdown(report: dict[str, Any]) -> str:
    latency = report["latency_ms"]
    lines = [
        "# Current ICTU Benchmark Results",
        "",
        f"- Dataset: `{report['dataset_path']}`",
        f"- Dataset SHA-256: `{report['dataset_sha256']}`",
        f"- Generated at: `{report['generated_at']}`",
        f"- Router mode requested: `{report['router_mode_requested']}`",
        f"- Route Accuracy: **{report['route_accuracy']:.2%}**",
        f"- Source Top-1: **{report['source_top1']:.2%}**",
        f"- Source Top-3: **{report['source_top3']:.2%}**",
        f"- MRR: **{report['mrr']:.4f}**",
        f"- Fallback count: **{report['fallback_count']}**",
        (
            "- Latency ms: "
            f"min={latency['min']}, max={latency['max']}, mean={latency['mean']}, "
            f"median={latency['median']}, p95={latency['p95']}"
        ),
        "",
        "## Cases",
        "",
        "| ID | Router mode | Selected tool | Source rank | Latency ms | Result |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for case in report["cases"]:
        source_rank = case["source_rank"] if case["source_rank"] is not None else "-"
        lines.append(
            f"| {case['id']} | {case['router_mode']} | {case['selected_tool']} | "
            f"{source_rank} | {case['latency_ms']} | {'pass' if case['passed'] else 'fail'} |"
        )

    lines.extend(["", "## Wrong Cases And Reasons", ""])
    if not report["wrong_cases"]:
        lines.append("- None.")
    else:
        for case in report["wrong_cases"]:
            lines.append(
                f"- `{case['id']}`: {', '.join(case['failure_reasons'])}; "
                f"selected_tool=`{case['selected_tool']}`; source_rank={case['source_rank']}."
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the fixed ICTU 30-question benchmark without modifying its dataset.")
    parser.add_argument(
        "--router-mode",
        choices=("controlled", "keyword"),
        default="controlled",
        help="controlled uses the production router; keyword runs the deterministic controlled keyword router.",
    )
    args = parser.parse_args()

    report = evaluate_dataset(router_mode=args.router_mode)
    OUTPUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_MD.write_text(build_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "dataset": report["dataset_path"],
                "total_cases": report["total_cases"],
                "route_accuracy": report["route_accuracy"],
                "source_top1": report["source_top1"],
                "source_top3": report["source_top3"],
                "mrr": report["mrr"],
                "fallback_count": report["fallback_count"],
                "output_json": OUTPUT_JSON.relative_to(ROOT).as_posix(),
                "output_md": OUTPUT_MD.relative_to(ROOT).as_posix(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
