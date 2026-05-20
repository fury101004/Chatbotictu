from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.eval_tracker import EvalTracker


class EvalTrackerTests(unittest.IsolatedAsyncioTestCase):
    async def test_logging_and_metrics_calculation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tracker = EvalTracker(Path(temp_dir) / "eval_log.db")
            await tracker.log_response(
                query="co nguon",
                answer_length=120,
                sources_returned=2,
                latency_ms=100,
                has_sources=True,
                user_thumbs_up=True,
            )
            await tracker.log_response(
                query="khong co nguon",
                answer_length=20,
                sources_returned=0,
                latency_ms=300,
                has_sources=False,
                user_thumbs_up=False,
            )

            metrics = await tracker.metrics(hours=24)

        self.assertEqual(metrics["total_queries"], 2)
        self.assertEqual(metrics["avg_latency_ms"], 200)
        self.assertEqual(metrics["source_hit_rate"], 0.5)
        self.assertEqual(metrics["thumbs_up_rate"], 0.5)
        self.assertEqual(metrics["failing_queries"], ["khong co nguon"])

    async def test_csv_export_contains_header_and_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tracker = EvalTracker(Path(temp_dir) / "eval_log.db")
            await tracker.log_response(
                query="hoc phi",
                answer_length=80,
                sources_returned=1,
                latency_ms=42,
                has_sources=True,
            )

            csv_text = await tracker.export_csv()

        self.assertIn("timestamp,query,answer_length,sources_returned,latency_ms,has_sources,user_thumbs_up", csv_text)
        self.assertIn("hoc phi", csv_text)


if __name__ == "__main__":
    unittest.main()

