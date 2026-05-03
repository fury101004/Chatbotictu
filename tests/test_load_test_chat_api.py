from __future__ import annotations

import unittest

from tools.evaluation.load_test_chat_api import RequestResult, summarize_results


class LoadTestSummaryTests(unittest.TestCase):
    def test_summarize_results_includes_429_ratio(self) -> None:
        results = [
            RequestResult(status_code=200, latency_ms=120.0),
            RequestResult(status_code=200, latency_ms=150.0),
            RequestResult(status_code=429, latency_ms=90.0),
            RequestResult(status_code=500, latency_ms=200.0, error="server error"),
        ]

        summary = summarize_results(results, elapsed_s=2.0)

        self.assertEqual(summary["total_requests"], 4)
        self.assertEqual(summary["status_code_counts"][200], 2)
        self.assertEqual(summary["status_code_counts"][429], 1)
        self.assertEqual(summary["rate_limit_429_count"], 1)
        self.assertEqual(summary["rate_limit_429_ratio"], 0.25)
        self.assertEqual(summary["success_count"], 2)
        self.assertEqual(summary["error_count"], 2)
        self.assertGreater(summary["latency_ms"]["p95"], 0.0)


if __name__ == "__main__":
    unittest.main()
