from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx


@dataclass(slots=True)
class RequestResult:
    status_code: int
    latency_ms: float
    error: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load test /api/v1/chat and monitor 429 behavior.")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000", help="Base URL of running API server.")
    parser.add_argument("--partner-key", default=os.getenv("PARTNER_API_KEY", ""), help="Partner key for /auth/token.")
    parser.add_argument("--message", default="Điều kiện xét học bổng là gì?", help="Prompt used for load requests.")
    parser.add_argument("--session-prefix", default="load-test", help="Session id prefix.")
    parser.add_argument("--total-requests", type=int, default=120, help="Total chat requests to send.")
    parser.add_argument("--concurrency", type=int, default=12, help="Concurrent in-flight requests.")
    parser.add_argument("--timeout", type=float, default=45.0, help="Per-request timeout in seconds.")
    parser.add_argument(
        "--metrics-endpoint",
        default="/api/v1/metrics/rate-limit-429",
        help="Endpoint path for 429 metrics after load test.",
    )
    parser.add_argument(
        "--reset-metrics-before-run",
        action="store_true",
        help="Reset 429 counters before sending load traffic.",
    )
    parser.add_argument(
        "--output",
        default="reports/load_test_chat_api_report.json",
        help="JSON report output path.",
    )
    return parser.parse_args()


def _percentile(latencies: list[float], ratio: float) -> float:
    if not latencies:
        return 0.0
    if ratio <= 0:
        return min(latencies)
    if ratio >= 1:
        return max(latencies)

    sorted_values = sorted(latencies)
    index = (len(sorted_values) - 1) * ratio
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return sorted_values[lower]
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def summarize_results(results: list[RequestResult], elapsed_s: float) -> dict[str, Any]:
    status_counts = Counter(item.status_code for item in results)
    latencies = [item.latency_ms for item in results if item.latency_ms >= 0]
    errors = [item.error for item in results if item.error]
    total = len(results)
    success_count = sum(count for code, count in status_counts.items() if 200 <= code < 300)
    rate_429 = status_counts.get(429, 0)

    return {
        "total_requests": total,
        "elapsed_seconds": round(elapsed_s, 3),
        "requests_per_second": round((total / elapsed_s) if elapsed_s > 0 else 0.0, 3),
        "success_count": success_count,
        "error_count": total - success_count,
        "status_code_counts": dict(status_counts),
        "rate_limit_429_count": rate_429,
        "rate_limit_429_ratio": round((rate_429 / total) if total else 0.0, 4),
        "latency_ms": {
            "min": round(min(latencies), 3) if latencies else 0.0,
            "max": round(max(latencies), 3) if latencies else 0.0,
            "avg": round(statistics.mean(latencies), 3) if latencies else 0.0,
            "p50": round(_percentile(latencies, 0.50), 3) if latencies else 0.0,
            "p95": round(_percentile(latencies, 0.95), 3) if latencies else 0.0,
            "p99": round(_percentile(latencies, 0.99), 3) if latencies else 0.0,
        },
        "sample_errors": errors[:20],
    }


async def _auth_token(base_url: str, partner_key: str, timeout: float) -> str:
    if not partner_key:
        raise RuntimeError("Missing partner key. Provide --partner-key or PARTNER_API_KEY env.")

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{base_url}/api/v1/auth/token", data={"partner_key": partner_key})
        response.raise_for_status()
        payload = response.json()
        token = str(payload.get("access_token", "")).strip()
        if not token:
            raise RuntimeError("Auth token response missing access_token.")
        return token


async def _request_chat(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    token: str,
    message: str,
    session_id: str,
) -> RequestResult:
    start = time.perf_counter()
    try:
        response = await client.post(
            f"{base_url}/api/v1/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "message": message,
                "session_id": session_id,
                "llm_model": "auto",
            },
        )
        latency_ms = (time.perf_counter() - start) * 1000
        return RequestResult(status_code=response.status_code, latency_ms=latency_ms)
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        return RequestResult(status_code=0, latency_ms=latency_ms, error=str(exc))


async def run_load_test(args: argparse.Namespace) -> dict[str, Any]:
    base_url = args.base_url.rstrip("/")
    token = await _auth_token(base_url, args.partner_key, args.timeout)

    async with httpx.AsyncClient(timeout=args.timeout) as client:
        if args.reset_metrics_before_run:
            await client.post(
                f"{base_url}/api/v1/metrics/rate-limit-429/reset",
                headers={"Authorization": f"Bearer {token}"},
            )

        semaphore = asyncio.Semaphore(max(1, args.concurrency))
        results: list[RequestResult] = []

        async def worker(index: int) -> None:
            async with semaphore:
                result = await _request_chat(
                    client,
                    base_url=base_url,
                    token=token,
                    message=args.message,
                    session_id=f"{args.session_prefix}-{index}",
                )
                results.append(result)

        started = time.perf_counter()
        await asyncio.gather(*(worker(i) for i in range(args.total_requests)))
        elapsed_s = max(time.perf_counter() - started, 1e-6)
        summary = summarize_results(results, elapsed_s)

        metrics_payload: dict[str, Any] | None = None
        try:
            metrics_response = await client.get(
                f"{base_url}{args.metrics_endpoint}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if metrics_response.status_code == 200:
                metrics_payload = metrics_response.json()
        except Exception:
            metrics_payload = None

    return {
        "generated_at": datetime.now().isoformat(),
        "base_url": base_url,
        "message": args.message,
        "total_requests": args.total_requests,
        "concurrency": args.concurrency,
        "summary": summary,
        "api_429_metrics": metrics_payload,
    }


def main() -> None:
    args = parse_args()
    report = asyncio.run(run_load_test(args))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = report["summary"]
    print(f"Total requests: {summary['total_requests']}")
    print(f"Success: {summary['success_count']} | Errors: {summary['error_count']}")
    print(f"429 count: {summary['rate_limit_429_count']} ({summary['rate_limit_429_ratio']:.2%})")
    print(f"RPS: {summary['requests_per_second']}")
    print(
        "Latency ms | avg={avg} p95={p95} p99={p99}".format(
            avg=summary["latency_ms"]["avg"],
            p95=summary["latency_ms"]["p95"],
            p99=summary["latency_ms"]["p99"],
        )
    )
    print(f"Report: {output_path}")


if __name__ == "__main__":
    main()
