from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from starlette.requests import Request

import main
import services.llm.llm_service as llm_service
from config import middleware
from config.settings import settings
from services.llm.rate_limit_monitor import record_429, reset_429_stats, snapshot_429_stats


class RateLimitMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_429_stats()

    def tearDown(self) -> None:
        reset_429_stats()

    def test_record_and_snapshot_429(self) -> None:
        record_429("api_rate_limiter", detail="too many requests", metadata={"path": "/api/v1/chat"})
        record_429("llm_provider", detail="status code 429")

        stats = snapshot_429_stats(limit_recent=10)

        self.assertEqual(stats["totals"]["all"], 2)
        self.assertEqual(stats["totals"]["api_rate_limiter"], 1)
        self.assertEqual(stats["totals"]["llm_provider"], 1)
        self.assertEqual(stats["recent_event_count"], 2)

    def test_rate_limit_handler_sets_retry_after_and_records_event(self) -> None:
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/chat",
                "raw_path": b"/api/v1/chat",
                "headers": [],
                "query_string": b"",
                "scheme": "http",
                "server": ("testserver", 80),
                "client": ("127.0.0.1", 9000),
                "root_path": "",
            }
        )

        response = middleware._rate_limit_exceeded_handler(request, RuntimeError("429"))

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers.get("Retry-After"), "60")
        stats = snapshot_429_stats(limit_recent=5)
        self.assertEqual(stats["totals"].get("api_rate_limiter"), 1)


class RateLimitMetricsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_429_stats()

    def tearDown(self) -> None:
        reset_429_stats()

    def _get_token(self, client: TestClient) -> str:
        response = client.post("/api/v1/auth/token", data={"partner_key": settings.PARTNER_API_KEY})
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    def test_metrics_endpoint_returns_recorded_429_events(self) -> None:
        record_429("api_rate_limiter", detail="burst traffic")
        client = TestClient(main.app)
        token = self._get_token(client)

        response = client.get(
            "/api/v1/metrics/rate-limit-429?limit_recent=5",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["totals"]["api_rate_limiter"], 1)
        self.assertEqual(payload["totals"]["all"], 1)
        self.assertEqual(payload["recent_event_count"], 1)

    def test_metrics_reset_endpoint_clears_counters(self) -> None:
        record_429("llm_provider", detail="model-limited")
        client = TestClient(main.app)
        token = self._get_token(client)

        reset_response = client.post(
            "/api/v1/metrics/rate-limit-429/reset",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(reset_response.status_code, 200)

        stats_response = client.get(
            "/api/v1/metrics/rate-limit-429",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(stats_response.status_code, 200)
        self.assertEqual(stats_response.json()["totals"], {})


class LLMRateLimitTrackingTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_429_stats()
        llm_service.get_model.cache_clear()
        llm_service._MODEL_ROTATION_INDEX = 0

    def tearDown(self) -> None:
        reset_429_stats()
        llm_service.get_model.cache_clear()
        llm_service._MODEL_ROTATION_INDEX = 0

    @patch.dict(
        os.environ,
        {
            "GROQ_API_KEY": "test-key",
            "GROQ_MODEL_ORDER": "model-a",
            "LLM_PROVIDER_ORDER": "groq",
        },
        clear=True,
    )
    def test_generate_content_records_llm_provider_429(self) -> None:
        request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
        response = httpx.Response(429, request=request, text="Too Many Requests")
        rate_limit_error = httpx.HTTPStatusError("429 too many requests", request=request, response=response)

        with patch("services.llm.llm_service._call_groq", side_effect=rate_limit_error):
            with self.assertRaises(RuntimeError):
                llm_service.generate_content_with_fallback("xin chao")

        stats = snapshot_429_stats(limit_recent=10)
        self.assertEqual(stats["totals"].get("llm_provider"), 1)
        self.assertEqual(stats["totals"].get("all"), 1)


if __name__ == "__main__":
    unittest.main()

