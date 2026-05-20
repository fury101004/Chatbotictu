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


def _csrf_from_login_page(client: TestClient, path: str = "/login") -> str:
    login_page = client.get(path)
    csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', login_page.text)
    assert csrf_match is not None
    return csrf_match.group(1)


def _login_as_admin(client: TestClient) -> None:
    csrf_token = _csrf_from_login_page(client)
    response = client.post(
        "/login",
        data={
            "username": settings.ADMIN_USERNAME,
            "password": settings.ADMIN_PASSWORD,
            "next_path": "/",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def _login_as_user(client: TestClient) -> None:
    csrf_token = _csrf_from_login_page(client)
    response = client.post(
        "/login",
        data={
            "username": settings.USER_USERNAME,
            "password": settings.USER_PASSWORD,
            "next_path": "/",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/chat"


def _csrf_from_chat_page_text(page_text: str) -> str:
    csrf_match = re.search(r'id="csrfToken" value="([^"]+)"', page_text)
    assert csrf_match is not None
    return csrf_match.group(1)


def _csrf_from_chat_page(client: TestClient) -> str:
    chat_page = client.get("/chat")
    assert chat_page.status_code == 200
    return _csrf_from_chat_page_text(chat_page.text)


def _nav_html(page_text: str) -> str:
    start = page_text.find('<header class="navbar"')
    end = page_text.find("</header>")
    assert start >= 0 and end >= start
    return page_text[start : end + len("</header>")]


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
        self.assertIn("/login", response.headers["location"])

    def test_chat_page_redirects_to_login_when_not_authenticated(self) -> None:
        client = TestClient(main.app)
        response = client.get("/chat", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("/login", response.headers["location"])

    def test_admin_login_allows_access_to_admin_page(self) -> None:
        client = TestClient(main.app)
        csrf_token = _csrf_from_login_page(client, "/admin/login?next=/data-loader")

        login_response = client.post(
            "/admin/login",
            data={
                "username": settings.ADMIN_USERNAME,
                "password": settings.ADMIN_PASSWORD,
                "next_path": "/data-loader",
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )
        self.assertEqual(login_response.status_code, 303)
        self.assertEqual(login_response.headers["location"], "/")

        admin_page = client.get("/data-loader")
        self.assertEqual(admin_page.status_code, 200)

    def test_user_login_shows_only_chat_menu_and_blocks_admin_pages(self) -> None:
        client = TestClient(main.app)
        _login_as_user(client)

        chat_page = client.get("/chat")
        nav_html = _nav_html(chat_page.text)
        self.assertEqual(chat_page.status_code, 200)
        self.assertIn("Trò chuyện", nav_html)
        self.assertIn("Đăng xuất", nav_html)
        self.assertNotIn("Trang chủ", nav_html)
        self.assertNotIn("Upload kiến thức", nav_html)
        self.assertNotIn("Kho vector", nav_html)
        self.assertNotIn("Kho tri thức", nav_html)
        self.assertNotIn("Cấu hình", nav_html)
        self.assertNotIn("Lịch sử chat", nav_html)
        self.assertNotIn("Đăng xuất admin", nav_html)

        for admin_path in (
            "/",
            "/data-loader",
            "/upload",
            "/vector-manager",
            "/vector-store",
            "/knowledge-base",
            "/knowledge",
            "/config",
            "/settings",
            "/history",
            "/admin",
            "/admin/login",
        ):
            response = client.get(admin_path, follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/chat")

    def test_admin_menu_contains_all_admin_items(self) -> None:
        client = TestClient(main.app)
        _login_as_admin(client)

        response = client.get("/")
        nav_html = _nav_html(response.text)
        self.assertEqual(response.status_code, 200)
        for label in (
            "Trang chủ",
            "Trò chuyện",
            "Upload kiến thức",
            "Kho vector",
            "Kho tri thức",
            "Cấu hình",
            "Lịch sử chat",
            "Đăng xuất admin",
        ):
            self.assertIn(label, nav_html)

    def test_logout_clears_session_and_redirects_to_login(self) -> None:
        client = TestClient(main.app)
        _login_as_user(client)

        logout_response = client.get("/logout", follow_redirects=False)
        self.assertEqual(logout_response.status_code, 303)
        self.assertEqual(logout_response.headers["location"], "/login")

        chat_response = client.get("/chat", follow_redirects=False)
        self.assertEqual(chat_response.status_code, 303)
        self.assertIn("/login", chat_response.headers["location"])

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

    def test_chat_rejects_invalid_csrf(self) -> None:
        client = TestClient(main.app)
        _login_as_user(client)

        response = client.post(
            "/chat",
            data={"message": "Xin chao", "session_id": "default", "csrf_token": "invalid"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json().get("detail"), "CSRF Invalid!")

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
            _login_as_user(client_a)
            _login_as_user(client_b)

            csrf_a = _csrf_from_chat_page(client_a)
            csrf_b = _csrf_from_chat_page(client_b)
            client_a.post("/chat", data={"message": "A", "session_id": "default", "csrf_token": csrf_a})
            client_b.post("/chat", data={"message": "B", "session_id": "default", "csrf_token": csrf_b})

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
