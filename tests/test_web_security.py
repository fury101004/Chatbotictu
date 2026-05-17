from __future__ import annotations

from datetime import datetime, timedelta
import re
import unittest
from unittest.mock import AsyncMock, patch

import jwt
from fastapi.testclient import TestClient

import main
from config.settings import settings
from config.rag_tools import get_tool_upload_dir, resolve_upload_source_path


class UploadPathSecurityTests(unittest.TestCase):
    def test_resolve_upload_source_path_blocks_parent_traversal(self) -> None:
        tool_dir = get_tool_upload_dir("student_faq_rag").resolve()
        resolved = resolve_upload_source_path("uploads/student_faq_rag/../../outside.txt").resolve()

        self.assertTrue(resolved.is_relative_to(tool_dir))
        self.assertEqual(resolved.name, "outside.txt")


class WebCsrfSecurityTests(unittest.TestCase):
    def test_admin_pages_redirect_to_login_when_not_authenticated(self) -> None:
        client = TestClient(main.app)
        response = client.get("/data-loader", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("/admin/login", response.headers["location"])

    def test_public_chat_page_does_not_require_admin_login(self) -> None:
        client = TestClient(main.app)
        response = client.get("/chat")

        self.assertEqual(response.status_code, 200)

    def test_admin_login_allows_access_to_admin_page(self) -> None:
        client = TestClient(main.app)
        login_page = client.get("/admin/login?next=/data-loader")
        csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', login_page.text)
        self.assertIsNotNone(csrf_match)

        login_response = client.post(
            "/admin/login",
            data={
                "username": settings.ADMIN_USERNAME,
                "password": settings.ADMIN_PASSWORD,
                "next_path": "/data-loader",
                "csrf_token": csrf_match.group(1),
            },
            follow_redirects=False,
        )
        self.assertEqual(login_response.status_code, 303)
        self.assertEqual(login_response.headers["location"], "/data-loader")

        admin_page = client.get("/data-loader")
        self.assertEqual(admin_page.status_code, 200)

    def test_upload_rejects_invalid_csrf(self) -> None:
        client = TestClient(main.app)
        response = client.post(
            "/upload",
            data={
                "tool_name": "student_faq_rag",
                "client_start_time": "1",
                "client_total_size": "1",
                "csrf_token": "invalid",
            },
            files=[("files", ("guide.md", b"# Guide", "text/markdown"))],
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json().get("msg"), "CSRF Invalid!")

    def test_update_config_rejects_invalid_csrf(self) -> None:
        client = TestClient(main.app)
        response = client.post(
            "/update-config",
            data={
                "chunk_size": "1000",
                "chunk_overlap": "200",
                "bot_rules": "Test prompt",
                "reingest": "false",
                "csrf_token": "invalid",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json().get("msg"), "CSRF Invalid!")

    def test_delete_chunk_rejects_invalid_csrf(self) -> None:
        client = TestClient(main.app)
        response = client.post(
            "/delete-chunk",
            data={"chunk_id": "chunk-1", "csrf_token": "invalid"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json().get("status"), "error")
        self.assertEqual(response.json().get("error"), "CSRF Invalid!")


class ChatSessionIsolationTests(unittest.TestCase):
    def test_chat_route_uses_per_browser_session_id_when_default_is_sent(self) -> None:
        mock_chat = AsyncMock(return_value={"response": "ok"})
        with patch("controllers.web_controller.process_chat_message", mock_chat):
            client_a = TestClient(main.app)
            client_b = TestClient(main.app)

            client_a.get("/chat")
            client_b.get("/chat")
            client_a.post("/chat", data={"message": "A", "session_id": "default"})
            client_b.post("/chat", data={"message": "B", "session_id": "default"})

        session_a = mock_chat.await_args_list[0].args[1]
        session_b = mock_chat.await_args_list[1].args[1]

        self.assertNotEqual(session_a, "default")
        self.assertNotEqual(session_b, "default")
        self.assertNotEqual(session_a, session_b)


class ApiAuthSecurityTests(unittest.TestCase):
    def test_api_rejects_token_with_wrong_subject(self) -> None:
        client = TestClient(main.app)
        wrong_subject_token = jwt.encode(
            {"exp": datetime.utcnow() + timedelta(minutes=5), "sub": "student"},
            settings.JWT_SECRET,
            algorithm="HS256",
        )

        response = client.get(
            "/api/v1/metrics/rate-limit-429",
            headers={"Authorization": f"Bearer {wrong_subject_token}"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json().get("detail"), "Invalid token subject")


if __name__ == "__main__":
    unittest.main()
