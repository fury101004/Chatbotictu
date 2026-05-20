from __future__ import annotations

import unittest

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from middleware.input_guard import InputGuardMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.post("/api/chat")
    async def chat(request: Request):
        return await request.json()

    @app.post("/upload")
    async def upload():
        return {"status": "accepted"}

    @app.post("/api/auth/token")
    async def token():
        return {"access_token": "test"}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.add_middleware(
        InputGuardMiddleware,
        max_message_chars=5,
        max_upload_bytes=1,
        token_limit=2,
        token_window_seconds=60,
    )
    return app


class InputGuardTests(unittest.TestCase):
    def test_adds_request_id_header_to_every_response(self) -> None:
        response = TestClient(_build_app()).get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers.get("x-request-id"))

    def test_rejects_chat_message_over_limit(self) -> None:
        response = TestClient(_build_app()).post("/api/chat", json={"message": "too long"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("Maximum is 5 characters", response.json()["detail"])
        self.assertTrue(response.headers.get("x-request-id"))

    def test_rejects_upload_over_declared_limit(self) -> None:
        response = TestClient(_build_app()).post(
            "/upload",
            files=[("files", ("guide.md", b"abc", "text/markdown"))],
        )

        self.assertEqual(response.status_code, 413)
        self.assertTrue(response.headers.get("x-request-id"))

    def test_rate_limits_token_endpoint_by_ip(self) -> None:
        client = TestClient(_build_app())

        self.assertEqual(client.post("/api/auth/token", data={"partner_key": "x"}).status_code, 200)
        self.assertEqual(client.post("/api/auth/token", data={"partner_key": "x"}).status_code, 200)
        limited = client.post("/api/auth/token", data={"partner_key": "x"})

        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.headers.get("retry-after"), "60")


if __name__ == "__main__":
    unittest.main()

