"""
scripts/run_evaluator.py
========================
Đánh giá định kỳ chất lượng retrieval với các metric:
  - exact_year_retrieval: % câu hỏi có năm được retrieve đúng file năm đó
  - source_precision@k (k=3,5,10)
  - no_answer_behavior: test câu hỏi ngoài phạm vi
  - citation_presence: % response có trả về sources

Chạy:
    python scripts/run_evaluator.py
    python scripts/run_evaluator.py --output eval_report.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def _find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "main.py").exists() and (parent / "services").is_dir():
            return parent
    return Path(__file__).resolve().parents[1]


ROOT = _find_repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.rag_tools import FALLBACK_RAG_NODE  # noqa: E402
from services.rag.rag_service import route_rag_tool, retrieve_tool_context, retrieve_fallback_context  # noqa: E402
from services.vector.vector_store_service import embedding_backend_ready, get_collection  # noqa: E402


# ── Evaluation test cases ───────────────────────────────────────────

@dataclass
class EvalCase:
    id: str
    question: str
    expected_year: str = ""
    expected_sources: list[str] = field(default_factory=list)
    is_out_of_scope: bool = False


YEAR_CASES = [
    EvalCase("yr01", "Sổ tay sinh viên 2025-2026 áp dụng cho đối tượng nào?",
             "2025-2026", ["8. SO TAY SINH VIEN 2025-2026"]),
    EvalCase("yr02", "Sổ tay 2024-2025 quy định gì về email sinh viên?",
             "2024-2025", ["7. SO TAY SINH VIEN 2024-2025"]),
    EvalCase("yr03", "Năm 2023-2024 trường ICTU có bao nhiêu ngành?",
             "2023-2024", ["6. SO TAY SINH VIEN 2023-2024"]),
    EvalCase("yr04", "Triết lý giáo dục trong sổ tay 2022-2023?",
             "2022-2023", ["5. SO TAY SINH VIEN 2022-2023"]),
    EvalCase("yr05", "Sổ tay sinh viên 2021-2022 nêu quyền lợi gì?",
             "2021-2022", ["4. SO TAY SINH VIEN 2021-2022"]),
]

GENERAL_CASES = [
    EvalCase("gen01", "Điều kiện tốt nghiệp đại học tại ICTU?",
             expected_sources=["SO TAY SINH VIEN"]),
    EvalCase("gen02", "Sinh viên đăng ký tối thiểu bao nhiêu tín chỉ?",
             expected_sources=["SO TAY SINH VIEN"]),
    EvalCase("gen03", "Quy định về điểm rèn luyện của sinh viên?",
             expected_sources=["SO TAY SINH VIEN"]),
    EvalCase("gen04", "Người học có quyền gì tại ICTU?",
             expected_sources=["SO TAY SINH VIEN"]),
    EvalCase("gen05", "Bảo hiểm y tế sinh viên đóng ở đâu?",
             expected_sources=["SO TAY SINH VIEN"]),
]

OUT_OF_SCOPE_CASES = [
    EvalCase("oos01", "Giá vàng hôm nay là bao nhiêu?", is_out_of_scope=True),
    EvalCase("oos02", "Cách nấu bún chả Hà Nội?", is_out_of_scope=True),
    EvalCase("oos03", "Thủ đô của Australia là gì?", is_out_of_scope=True),
    EvalCase("oos04", "Lionel Messi cao bao nhiêu?", is_out_of_scope=True),
    EvalCase("oos05", "Bitcoin có phải tiền tệ hợp pháp không?", is_out_of_scope=True),
]

ALL_CASES = YEAR_CASES + GENERAL_CASES + OUT_OF_SCOPE_CASES


# ── Metric functions ───────────────────────────────────────────────

def _normalize(text: str) -> str:
    import unicodedata
    decomposed = unicodedata.normalize("NFKD", str(text or "").casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _retrieve(question: str, case_id: str) -> dict[str, Any]:
    predicted_tool, route_name = route_rag_tool(question)
    session_id = f"eval_{case_id}"

    if predicted_tool == FALLBACK_RAG_NODE:
        r = retrieve_fallback_context(question, session_id=session_id, route_name=route_name)
    else:
        r = retrieve_tool_context(message=question, session_id=session_id,
                                  tool_name=predicted_tool, route_name=route_name)
    return {
        "tool": predicted_tool,
        "sources": r.sources,
        "chunks_used": r.chunks_used,
        "context_len": len(r.context_text or ""),
        "mode": r.mode,
    }


def exact_year_retrieval(cases: list[EvalCase]) -> dict[str, Any]:
    """% câu hỏi có năm học mà retrieval trả về đúng file của năm đó."""
    year_cases = [c for c in cases if c.expected_year]
    if not year_cases:
        return {"metric": "exact_year_retrieval", "value": 0, "total": 0, "hits": 0}

    hits = 0
    details = []
    for case in year_cases:
        r = _retrieve(case.question, case.id)
        year_in_source = any(case.expected_year in s for s in r["sources"])
        if year_in_source:
            hits += 1
        details.append({"id": case.id, "year": case.expected_year, "hit": year_in_source,
                         "sources": r["sources"][:3]})

    return {
        "metric": "exact_year_retrieval",
        "value": round(hits / len(year_cases), 4),
        "total": len(year_cases),
        "hits": hits,
        "details": details,
    }


def source_precision_at_k(cases: list[EvalCase], k_values: list[int] = None) -> dict[str, Any]:
    """Precision@K: % sources trong top-K chứa expected source."""
    if k_values is None:
        k_values = [3, 5, 10]

    source_cases = [c for c in cases if c.expected_sources and not c.is_out_of_scope]
    results = {f"precision@{k}": 0.0 for k in k_values}
    if not source_cases:
        return {"metric": "source_precision_at_k", "values": results, "total": 0}

    for k in k_values:
        hits = 0
        for case in source_cases:
            r = _retrieve(case.question, case.id)
            top_sources = r["sources"][:k]
            for expected in case.expected_sources:
                norm_exp = _normalize(expected)
                if any(norm_exp in _normalize(s) for s in top_sources):
                    hits += 1
                    break
        results[f"precision@{k}"] = round(hits / len(source_cases), 4)

    return {"metric": "source_precision_at_k", "values": results, "total": len(source_cases)}


def no_answer_behavior(cases: list[EvalCase]) -> dict[str, Any]:
    """Test: câu ngoài scope không nên retrieve được nguồn sổ tay ICTU có liên quan."""
    oos_cases = [c for c in cases if c.is_out_of_scope]
    if not oos_cases:
        return {"metric": "no_answer_behavior", "value": 0, "total": 0, "correct": 0}

    correct = 0
    details = []
    for case in oos_cases:
        r = _retrieve(case.question, case.id)
        # "correct" nếu không tìm thấy nguồn liên quan đến sổ tay
        no_ictu_source = not any("SO TAY" in s.upper() for s in r["sources"])
        few_chunks = r["chunks_used"] <= 2
        is_correct = no_ictu_source or few_chunks
        if is_correct:
            correct += 1
        details.append({"id": case.id, "correct": is_correct, "chunks": r["chunks_used"],
                         "sources": r["sources"][:3]})

    return {
        "metric": "no_answer_behavior",
        "value": round(correct / len(oos_cases), 4),
        "total": len(oos_cases),
        "correct": correct,
        "details": details,
    }


def citation_presence(cases: list[EvalCase]) -> dict[str, Any]:
    """% retrieval results có trả về ít nhất 1 source."""
    non_oos = [c for c in cases if not c.is_out_of_scope]
    if not non_oos:
        return {"metric": "citation_presence", "value": 0, "total": 0, "with_citation": 0}

    with_citation = 0
    for case in non_oos:
        r = _retrieve(case.question, case.id)
        if r["sources"]:
            with_citation += 1

    return {
        "metric": "citation_presence",
        "value": round(with_citation / len(non_oos), 4),
        "total": len(non_oos),
        "with_citation": with_citation,
    }


# ── Main ────────────────────────────────────────────────────────────

def run_evaluation() -> dict[str, Any]:
    t0 = time.time()
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "embedding_ready": embedding_backend_ready(),
        "vectorstore_chunks": get_collection().count(),
        "metrics": {},
    }

    print("📊 Đang chạy exact_year_retrieval...")
    report["metrics"]["exact_year_retrieval"] = exact_year_retrieval(ALL_CASES)

    print("📊 Đang chạy source_precision@k...")
    report["metrics"]["source_precision_at_k"] = source_precision_at_k(ALL_CASES)

    print("📊 Đang chạy no_answer_behavior...")
    report["metrics"]["no_answer_behavior"] = no_answer_behavior(ALL_CASES)

    print("📊 Đang chạy citation_presence...")
    report["metrics"]["citation_presence"] = citation_presence(ALL_CASES)

    report["elapsed_seconds"] = round(time.time() - t0, 2)
    return report


def print_report(report: dict) -> None:
    print("\n" + "=" * 60)
    print("📊 EVALUATOR REPORT")
    print("=" * 60)
    for name, data in report.get("metrics", {}).items():
        if "value" in data:
            print(f"  {name:30s}  {data['value']:.1%}")
        elif "values" in data:
            for k, v in data["values"].items():
                print(f"  {k:30s}  {v:.1%}")
    print(f"\n  Thời gian: {report.get('elapsed_seconds', 0)}s")
    print(f"  Chunks: {report.get('vectorstore_chunks', 0)}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluator định kỳ cho RAG pipeline ICTU")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "evaluation" / "evaluator_report.json")
    args = parser.parse_args()

    report = run_evaluation()
    print_report(report)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📝 Report: {args.output}")


if __name__ == "__main__":
    main()
