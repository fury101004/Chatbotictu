"""
tests/e2e_test_30_questions.py
==============================
Bộ test End-to-End 30 câu hỏi cho hệ thống RAG chatbot ICTU.
Bao gồm: quy chế học tập, học phí/học bổng, tốt nghiệp, chính sách SV,
câu hỏi ngoài phạm vi (no-answer), câu hỏi chỉ định năm học.

Chạy:
    python tests/e2e_test_30_questions.py
    python tests/e2e_test_30_questions.py --with-llm          # Gọi LLM thật
    python tests/e2e_test_30_questions.py --output results.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
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

from services.rag.rag_service import route_rag_tool, retrieve_tool_context, retrieve_fallback_context  # noqa: E402
from config.rag_tools import FALLBACK_RAG_NODE  # noqa: E402

# ── Test case definition ────────────────────────────────────────────

@dataclass
class TestCase:
    id: str
    category: str
    question: str
    expected_keywords: list[str]
    expected_tool: str = "any"
    expected_year: str = ""
    expected_source_contains: list[str] = field(default_factory=list)
    expect_no_answer: bool = False

@dataclass
class TestResult:
    id: str
    category: str
    question: str
    predicted_tool: str
    route_name: str
    retrieval_mode: str = ""
    chunks_used: int = 0
    sources: list[str] = field(default_factory=list)
    context_snippet: str = ""
    llm_answer: str = ""
    used_model: str = ""
    tool_match: bool = False
    keyword_hit: bool = False
    source_hit: bool = False
    year_match: bool = False
    no_answer_correct: bool = False
    passed: bool = False
    latency_ms: float = 0.0
    error: str = ""

# ── 30 test cases ───────────────────────────────────────────────────

TEST_CASES: list[TestCase] = [
    # ── Nhóm 1: Quy chế học tập (6 câu) ──
    TestCase("QC01", "quy_che_hoc_tap", "Sinh viên phải đăng ký tối thiểu bao nhiêu tín chỉ mỗi học kỳ chính?",
             ["tín chỉ", "đăng ký", "tối thiểu"], "student_handbook_rag"),
    TestCase("QC02", "quy_che_hoc_tap", "Sinh viên học lực yếu được đăng ký tối đa bao nhiêu tín chỉ?",
             ["yếu", "tín chỉ", "tối đa"], "student_handbook_rag"),
    TestCase("QC03", "quy_che_hoc_tap", "Học kỳ phụ được đăng ký tối đa bao nhiêu tín chỉ?",
             ["học kỳ phụ", "tín chỉ"], "student_handbook_rag"),
    TestCase("QC04", "quy_che_hoc_tap", "Điều kiện để sinh viên đạt danh hiệu Giỏi là gì?",
             ["giỏi", "danh hiệu", "điều kiện"], "student_handbook_rag"),
    TestCase("QC05", "quy_che_hoc_tap", "Thang điểm đánh giá kết quả học tập gồm những loại nào?",
             ["thang điểm", "đánh giá"], "student_handbook_rag"),
    TestCase("QC06", "quy_che_hoc_tap", "Sinh viên bị buộc thôi học trong trường hợp nào?",
             ["buộc thôi học", "trường hợp"], "student_handbook_rag"),

    # ── Nhóm 2: Học phí, học bổng (5 câu) ──
    TestCase("HP01", "hoc_phi_hoc_bong", "Mức học phí đại học chính quy tại ICTU là bao nhiêu?",
             ["học phí", "mức"], "school_policy_rag"),
    TestCase("HP02", "hoc_phi_hoc_bong", "Sinh viên nào được miễn giảm học phí?",
             ["miễn giảm", "học phí"], "school_policy_rag"),
    TestCase("HP03", "hoc_phi_hoc_bong", "Điều kiện để nhận học bổng khuyến khích học tập là gì?",
             ["học bổng", "khuyến khích", "điều kiện"], "school_policy_rag"),
    TestCase("HP04", "hoc_phi_hoc_bong", "Quy định về trợ cấp xã hội cho sinh viên như thế nào?",
             ["trợ cấp", "xã hội"], "school_policy_rag"),
    TestCase("HP05", "hoc_phi_hoc_bong", "Sinh viên đóng bảo hiểm y tế ở đâu và khi nào?",
             ["bảo hiểm", "y tế", "bhyt"], "student_faq_rag"),

    # ── Nhóm 3: Điều kiện tốt nghiệp (5 câu) ──
    TestCase("TN01", "tot_nghiep", "Điều kiện để sinh viên được xét tốt nghiệp là gì?",
             ["xét tốt nghiệp", "điều kiện"], "student_handbook_rag"),
    TestCase("TN02", "tot_nghiep", "Sinh viên cần có chứng chỉ gì để đủ điều kiện tốt nghiệp?",
             ["chứng chỉ", "tốt nghiệp"], "student_handbook_rag"),
    TestCase("TN03", "tot_nghiep", "Thời gian đào tạo tối đa cho bậc đại học là bao lâu?",
             ["thời gian", "đào tạo", "tối đa"], "student_handbook_rag"),
    TestCase("TN04", "tot_nghiep", "Quy trình xét tốt nghiệp diễn ra như thế nào?",
             ["quy trình", "xét tốt nghiệp"], "student_faq_rag"),
    TestCase("TN05", "tot_nghiep", "Sinh viên cần nộp chứng chỉ trước đợt xét tốt nghiệp bao lâu?",
             ["chứng chỉ", "nộp", "xét tốt nghiệp"], "student_faq_rag"),

    # ── Nhóm 4: Chính sách sinh viên (5 câu) ──
    TestCase("CS01", "chinh_sach_sv", "Người học tại ICTU có những quyền gì?",
             ["quyền", "người học"], "student_handbook_rag"),
    TestCase("CS02", "chinh_sach_sv", "Người học không được làm những hành vi nào?",
             ["hành vi", "không được"], "student_handbook_rag"),
    TestCase("CS03", "chinh_sach_sv", "Quy định về kỷ luật sinh viên tại ICTU như thế nào?",
             ["kỷ luật", "sinh viên"], "school_policy_rag"),
    TestCase("CS04", "chinh_sach_sv", "Điểm rèn luyện của sinh viên được đánh giá như thế nào?",
             ["điểm rèn luyện", "đánh giá"], "school_policy_rag"),
    TestCase("CS05", "chinh_sach_sv", "Giá trị cốt lõi của Trường ICTU là gì?",
             ["giá trị", "cốt lõi"], "student_handbook_rag"),

    # ── Nhóm 5: Ngoài phạm vi — test no-answer (4 câu) ──
    TestCase("NA01", "no_answer", "Giá iPhone 16 Pro Max hiện tại là bao nhiêu?",
             [], expect_no_answer=True),
    TestCase("NA02", "no_answer", "Thủ đô của nước Pháp là gì?",
             [], expect_no_answer=True),
    TestCase("NA03", "no_answer", "Cách nấu phở bò Hà Nội ngon nhất?",
             [], expect_no_answer=True),
    TestCase("NA04", "no_answer", "Bitcoin hôm nay giá bao nhiêu?",
             [], expect_no_answer=True),

    # ── Nhóm 6: Chỉ định năm học (5 câu) ──
    TestCase("YR01", "year_filter", "Sổ tay sinh viên 2025-2026 áp dụng cho đối tượng nào?",
             ["2025-2026", "đối tượng"], "student_handbook_rag", "2025-2026",
             ["8. SO TAY SINH VIEN 2025-2026"]),
    TestCase("YR02", "year_filter", "Trong sổ tay 2024-2025, triết lý giáo dục của Trường là gì?",
             ["2024-2025", "triết lý"], "student_handbook_rag", "2024-2025",
             ["7. SO TAY SINH VIEN 2024-2025"]),
    TestCase("YR03", "year_filter", "Sổ tay 2023-2024 quy định về email sinh viên như thế nào?",
             ["2023-2024", "email"], "student_handbook_rag", "2023-2024",
             ["6. SO TAY SINH VIEN 2023-2024"]),
    TestCase("YR04", "year_filter", "Sinh viên khóa 24 dùng sổ tay sinh viên năm học nào?",
             ["khóa 24", "sổ tay"], "student_handbook_rag"),
    TestCase("YR05", "year_filter", "Năm học 2022-2023 có bao nhiêu ngành đào tạo tại ICTU?",
             ["2022-2023", "ngành"], "student_handbook_rag", "2022-2023",
             ["5. SO TAY SINH VIEN 2022-2023"]),
]


# ── Evaluation logic ───────────────────────────────────────────────

def _normalize(text: str) -> str:
    import unicodedata
    decomposed = unicodedata.normalize("NFKD", str(text or "").casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _keyword_hit(context: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    norm_ctx = _normalize(context)
    hits = sum(1 for kw in keywords if _normalize(kw) in norm_ctx)
    return hits >= max(1, len(keywords) // 2)


def _source_hit(sources: list[str], expected: list[str]) -> bool:
    if not expected:
        return True
    for exp in expected:
        norm_exp = _normalize(exp)
        if any(norm_exp in _normalize(s) for s in sources):
            return True
    return False


def _tool_matches(expected: str, predicted: str) -> bool:
    return expected in ("any", "", "*") or predicted == expected


def evaluate_case(case: TestCase, *, with_llm: bool = False) -> TestResult:
    t0 = time.perf_counter()
    result = TestResult(
        id=case.id, category=case.category, question=case.question,
        predicted_tool="", route_name="",
    )

    try:
        predicted_tool, route_name = route_rag_tool(case.question)
        result.predicted_tool = predicted_tool
        result.route_name = route_name

        session_id = f"e2e_test_{case.id}"
        if predicted_tool == FALLBACK_RAG_NODE:
            retrieval = retrieve_fallback_context(case.question, session_id=session_id, route_name=route_name)
        else:
            retrieval = retrieve_tool_context(
                message=case.question, session_id=session_id,
                tool_name=predicted_tool, route_name=route_name,
            )

        result.retrieval_mode = retrieval.mode
        result.chunks_used = retrieval.chunks_used
        result.sources = retrieval.sources
        result.context_snippet = (retrieval.context_text or "")[:500]

        result.tool_match = _tool_matches(case.expected_tool, predicted_tool)
        result.keyword_hit = _keyword_hit(retrieval.context_text or "", case.expected_keywords)
        result.source_hit = _source_hit(retrieval.sources, case.expected_source_contains)

        if case.expected_year and retrieval.sources:
            result.year_match = any(case.expected_year in s for s in retrieval.sources)
        elif not case.expected_year:
            result.year_match = True

        if case.expect_no_answer:
            has_ictu_source = any("SO TAY" in s.upper() for s in retrieval.sources)
            result.no_answer_correct = not has_ictu_source or retrieval.chunks_used == 0
            result.passed = result.no_answer_correct
        else:
            result.passed = result.tool_match and result.keyword_hit and result.source_hit

        if with_llm and not case.expect_no_answer:
            try:
                from services.chat.multilingual_service import chat_multilingual
                answer, used_model = chat_multilingual(
                    case.question, retrieval.context_text or "", session_id,
                )
                result.llm_answer = answer or ""
                result.used_model = used_model or ""
            except Exception as exc:
                result.llm_answer = f"[LLM ERROR] {exc}"

    except Exception as exc:
        result.error = str(exc)
        result.passed = False

    result.latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    return result


# ── Report builder ──────────────────────────────────────────────────

def build_report(results: list[TestResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    categories = {}
    for r in results:
        cat = categories.setdefault(r.category, {"total": 0, "passed": 0})
        cat["total"] += 1
        if r.passed:
            cat["passed"] += 1

    latencies = [r.latency_ms for r in results]
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "total_cases": total,
        "passed": passed,
        "failed": total - passed,
        "accuracy": round(passed / total, 4) if total else 0,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
        "max_latency_ms": max(latencies) if latencies else 0,
        "categories": {
            cat: {"total": info["total"], "passed": info["passed"],
                  "accuracy": round(info["passed"] / info["total"], 4)}
            for cat, info in categories.items()
        },
        "failing_cases": [
            {"id": r.id, "category": r.category, "question": r.question,
             "predicted_tool": r.predicted_tool, "error": r.error}
            for r in results if not r.passed
        ],
        "cases": [asdict(r) for r in results],
    }


def print_report(report: dict) -> None:
    print("\n" + "=" * 70)
    print("📊 E2E TEST REPORT — 30 CÂU HỎI ICTU CHATBOT")
    print("=" * 70)
    print(f"Tổng: {report['total_cases']} | Pass: {report['passed']} | "
          f"Fail: {report['failed']} | Accuracy: {report['accuracy']:.1%}")
    print(f"Latency TB: {report['avg_latency_ms']}ms | Max: {report['max_latency_ms']}ms")
    print()
    print("Theo nhóm:")
    for cat, info in report["categories"].items():
        print(f"  {cat:20s}  {info['passed']}/{info['total']}  ({info['accuracy']:.0%})")
    if report["failing_cases"]:
        print(f"\n❌ Các ca thất bại ({len(report['failing_cases'])}):")
        for c in report["failing_cases"]:
            print(f"  {c['id']}: {c['question'][:60]}...")
            if c["error"]:
                print(f"    Error: {c['error'][:80]}")
    print("=" * 70)


# ── Main ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="E2E test 30 câu hỏi ICTU chatbot")
    parser.add_argument("--with-llm", action="store_true", help="Gọi LLM thật để sinh câu trả lời")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "evaluation" / "e2e_30_results.json")
    args = parser.parse_args()

    print(f"🚀 Chạy {len(TEST_CASES)} test cases (with_llm={args.with_llm})...\n")
    results = []
    for i, case in enumerate(TEST_CASES, 1):
        print(f"  [{i:2d}/{len(TEST_CASES)}] {case.id} — {case.question[:50]}...", end=" ")
        result = evaluate_case(case, with_llm=args.with_llm)
        status = "✅" if result.passed else "❌"
        print(f"{status} ({result.latency_ms}ms)")
        results.append(result)

    report = build_report(results)
    print_report(report)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📝 Report: {args.output}")


if __name__ == "__main__":
    main()
