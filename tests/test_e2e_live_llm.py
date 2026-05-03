from __future__ import annotations

import os
import unittest

from fastapi.testclient import TestClient

import main
from config.settings import settings
from services.llm_service import llm_network_available


def _run_live_e2e_enabled() -> bool:
    return os.getenv("RUN_LIVE_LLM_E2E", "").strip().lower() in {"1", "true", "yes", "on"}


@unittest.skipUnless(_run_live_e2e_enabled(), "Set RUN_LIVE_LLM_E2E=1 to run live LLM E2E tests.")
class LiveLLME2ETests(unittest.TestCase):
    def test_chat_api_returns_answer_with_real_llm_backend(self) -> None:
        if not llm_network_available(timeout=1.5):
            self.skipTest("No reachable LLM backend for live E2E.")

        client = TestClient(main.app)

        token_response = client.post("/api/v1/auth/token", data={"partner_key": settings.PARTNER_API_KEY})
        self.assertEqual(token_response.status_code, 200)
        token = token_response.json()["access_token"]

        response = client.post(
            "/api/v1/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "message": "Trả lời đúng 1 từ: OK",
                "session_id": "e2e-live-llm",
                "llm_model": "auto",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(str(payload.get("response", "")).strip())
        llm_model = str(payload.get("llm_model", "")).strip().lower()
        self.assertTrue(llm_model)
        self.assertFalse(llm_model.startswith("local:"))
        self.assertNotEqual(llm_model, "unconfigured")


if __name__ == "__main__":
    unittest.main()
