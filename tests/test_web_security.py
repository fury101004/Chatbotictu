from __future__ import annotations

from datetime import datetime, timedelta
import re
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

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


def _csrf_from_register_page(client: TestClient) -> str:
    register_page = client.get("/register")
    csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', register_page.text)
    assert csrf_match is not None
    return csrf_match.group(1)


def _unique_username(prefix: str = "new-user") -> str:
    return f"{prefix}-{uuid4().hex[:12]}@example.com"


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
    assert response.headers["location"] == "/"


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

    def test_home_page_redirects_to_login_when_not_authenticated(self) -> None:
        client = TestClient(main.app)
        response = client.get("/", follow_redirects=False)

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

    def test_user_login_shows_only_user_menu_and_blocks_admin_pages(self) -> None:
        client = TestClient(main.app)
        _login_as_user(client)

        home_page = client.get("/")
        nav_html = _nav_html(home_page.text)
        self.assertEqual(home_page.status_code, 200)
        self.assertIn("Khu vực sinh viên", home_page.text)
        self.assertIn("Phạm vi sử dụng", home_page.text)
        self.assertIn("Trang chủ", nav_html)
        self.assertIn("Trò chuyện", nav_html)
        self.assertIn("Lịch sử chat", nav_html)
        self.assertIn("Đăng xuất", nav_html)
        self.assertNotIn("Upload kiến thức", nav_html)
        self.assertNotIn("Kho vector", nav_html)
        self.assertNotIn("Kho tri thức", nav_html)
        self.assertNotIn("Cấu hình", nav_html)
        self.assertNotIn("Đánh giá", nav_html)
        self.assertNotIn("Đăng xuất admin", nav_html)

        chat_page = client.get("/chat")
        self.assertEqual(chat_page.status_code, 200)
        self.assertIn("Trang chủ", _nav_html(chat_page.text))

        history_page = client.get("/history")
        self.assertEqual(history_page.status_code, 200)
        self.assertIn("Lịch sử của bạn", history_page.text)
        self.assertNotIn("Vector Store", history_page.text)
        self.assertNotIn("Knowledge Base", history_page.text)

        login_redirect = client.get("/login", follow_redirects=False)
        self.assertEqual(login_redirect.status_code, 303)
        self.assertEqual(login_redirect.headers["location"], "/")

        admin_login_redirect = client.get("/admin/login", follow_redirects=False)
        self.assertEqual(admin_login_redirect.status_code, 303)
        self.assertEqual(admin_login_redirect.headers["location"], "/")

        register_redirect = client.get("/register", follow_redirects=False)
        self.assertEqual(register_redirect.status_code, 303)
        self.assertEqual(register_redirect.headers["location"], "/")

        for admin_path in (
            "/data-loader",
            "/upload",
            "/vector-manager",
            "/vector-store",
            "/knowledge-base",
            "/knowledge",
            "/config",
            "/settings",
            "/evaluation-dashboard",
            "/admin",
        ):
            response = client.get(admin_path, follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/chat")

    def test_register_user_then_login_and_block_admin_pages(self) -> None:
        client = TestClient(main.app)
        username = _unique_username()
        password = "secret123"
        csrf_token = _csrf_from_register_page(client)

        register_response = client.post(
            "/register",
            data={
                "full_name": "New Test User",
                "username": username,
                "password": password,
                "confirm_password": password,
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )
        self.assertEqual(register_response.status_code, 303)
        self.assertEqual(register_response.headers["location"], "/login?registered=1")

        success_page = client.get("/login?registered=1")
        self.assertIn("Đăng ký thành công", success_page.text)

        login_csrf = _csrf_from_login_page(client)
        login_response = client.post(
            "/login",
            data={
                "username": username,
                "password": password,
                "next_path": "/",
                "csrf_token": login_csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(login_response.status_code, 303)
        self.assertEqual(login_response.headers["location"], "/")

        home_page = client.get("/")
        self.assertEqual(home_page.status_code, 200)
        self.assertIn("Khu vực sinh viên", home_page.text)

        chat_page = client.get("/chat")
        self.assertEqual(chat_page.status_code, 200)

        admin_response = client.get("/admin", follow_redirects=False)
        self.assertEqual(admin_response.status_code, 303)
        self.assertEqual(admin_response.headers["location"], "/chat")

    def test_register_rejects_duplicate_username(self) -> None:
        client = TestClient(main.app)
        username = _unique_username("duplicate-user")
        password = "secret123"
        csrf_token = _csrf_from_register_page(client)
        first_response = client.post(
            "/register",
            data={
                "full_name": "Duplicate User",
                "username": username,
                "password": password,
                "confirm_password": password,
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )
        self.assertEqual(first_response.status_code, 303)

        duplicate_csrf = _csrf_from_register_page(client)
        duplicate_response = client.post(
            "/register",
            data={
                "full_name": "Duplicate User",
                "username": username.upper(),
                "password": password,
                "confirm_password": password,
                "csrf_token": duplicate_csrf,
            },
        )
        self.assertEqual(duplicate_response.status_code, 200)
        self.assertIn("Tài khoản đã tồn tại.", duplicate_response.text)

    def test_api_register_creates_user_and_rejects_duplicate_username(self) -> None:
        client = TestClient(main.app)
        username = _unique_username("api-register-user")
        payload = {
            "full_name": "API Register User",
            "username": username,
            "password": "secret123",
            "confirm_password": "secret123",
        }

        response = client.post("/api/register", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("status"), "ok")

        duplicate_response = client.post("/api/register", json={**payload, "username": username.upper()})
        self.assertEqual(duplicate_response.status_code, 409)
        self.assertEqual(duplicate_response.json().get("detail"), "Tài khoản đã tồn tại.")

    def test_register_rejects_password_mismatch(self) -> None:
        client = TestClient(main.app)
        csrf_token = _csrf_from_register_page(client)
        response = client.post(
            "/register",
            data={
                "full_name": "Mismatch User",
                "username": _unique_username("mismatch-user"),
                "password": "secret123",
                "confirm_password": "secret456",
                "csrf_token": csrf_token,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Mật khẩu không khớp.", response.text)

    def test_register_rejects_short_password(self) -> None:
        client = TestClient(main.app)
        csrf_token = _csrf_from_register_page(client)
        response = client.post(
            "/register",
            data={
                "full_name": "Short Password User",
                "username": _unique_username("short-password-user"),
                "password": "12345",
                "confirm_password": "12345",
                "csrf_token": csrf_token,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Mật khẩu phải có ít nhất 6 ký tự.", response.text)

    def test_register_rejects_blank_required_fields(self) -> None:
        client = TestClient(main.app)
        csrf_token = _csrf_from_register_page(client)
        response = client.post(
            "/register",
            data={
                "full_name": "",
                "username": "",
                "password": "",
                "confirm_password": "",
                "csrf_token": csrf_token,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Vui lòng nhập đầy đủ thông tin bắt buộc.", response.text)

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
            "Đánh giá",
            "Lịch sử chat",
            "Đăng xuất admin",
        ):
            self.assertIn(label, nav_html)

    def test_evaluation_dashboard_is_admin_only(self) -> None:
        anonymous = TestClient(main.app)
        anonymous_response = anonymous.get("/evaluation-dashboard", follow_redirects=False)
        self.assertEqual(anonymous_response.status_code, 303)
        self.assertIn("/login", anonymous_response.headers["location"])

        user_client = TestClient(main.app)
        _login_as_user(user_client)
        user_response = user_client.get("/evaluation-dashboard", follow_redirects=False)
        self.assertEqual(user_response.status_code, 303)
        self.assertEqual(user_response.headers["location"], "/chat")

        admin_client = TestClient(main.app)
        _login_as_admin(admin_client)
        admin_response = admin_client.get("/evaluation-dashboard")
        self.assertEqual(admin_response.status_code, 200)
        self.assertIn("ICTU Chatbot — Evaluation Dashboard", admin_response.text)
        self.assertIn("Bộ 30 câu hỏi kiểm thử ICTU", admin_response.text)

    def test_evaluation_api_requires_admin_session(self) -> None:
        anonymous = TestClient(main.app)
        anonymous_response = anonymous.get("/api/logs")
        self.assertEqual(anonymous_response.status_code, 401)

        user_client = TestClient(main.app)
        _login_as_user(user_client)
        user_response = user_client.get("/api/logs")
        self.assertEqual(user_response.status_code, 403)

        admin_client = TestClient(main.app)
        _login_as_admin(admin_client)
        admin_response = admin_client.get("/api/logs")
        self.assertEqual(admin_response.status_code, 200)
        self.assertIsInstance(admin_response.json(), list)

        questions_response = admin_client.get("/api/test-questions")
        self.assertEqual(questions_response.status_code, 200)
        question_ids = {item.get("id") for item in questions_response.json()}
        self.assertIn("local_001", question_ids)
        self.assertIn("web_015", question_ids)

    def test_feedback_summary_requires_admin_session(self) -> None:
        summary = {
            "total_feedback": 2,
            "positive_feedback": 1,
            "negative_feedback": 1,
            "positive_rate": 50.0,
        }

        with patch("controllers.api_controller.get_feedback_summary", AsyncMock(return_value=summary)):
            anonymous = TestClient(main.app)
            anonymous_response = anonymous.get("/api/feedback/summary")
            self.assertEqual(anonymous_response.status_code, 401)

            user_client = TestClient(main.app)
            _login_as_user(user_client)
            user_response = user_client.get("/api/feedback/summary")
            self.assertEqual(user_response.status_code, 403)

            admin_client = TestClient(main.app)
            _login_as_admin(admin_client)
            admin_response = admin_client.get("/api/feedback/summary")

        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual(admin_response.json(), summary)

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

    def test_chat_feedback_requires_login_and_csrf(self) -> None:
        anonymous = TestClient(main.app)
        anonymous_response = anonymous.post(
            "/chat/feedback",
            data={
                "session_id": "feedback-1",
                "question": "Q",
                "answer": "A",
                "thumbs_up": "1",
                "csrf_token": "missing",
            },
        )
        self.assertEqual(anonymous_response.status_code, 401)

        client = TestClient(main.app)
        _login_as_user(client)
        response = client.post(
            "/chat/feedback",
            data={
                "session_id": "feedback-1",
                "question": "Q",
                "answer": "A",
                "thumbs_up": "1",
                "csrf_token": "invalid",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json().get("detail"), "CSRF Invalid!")

    def test_chat_feedback_saves_for_logged_in_user(self) -> None:
        client = TestClient(main.app)
        _login_as_user(client)
        csrf_token = _csrf_from_chat_page(client)

        with patch("controllers.web_controller.save_user_feedback", AsyncMock(return_value=42)) as save_mock:
            response = client.post(
                "/chat/feedback",
                data={
                    "session_id": "feedback-1",
                    "question": "Dieu kien tot nghiep la gi?",
                    "answer": "Can du tin chi theo quy dinh.",
                    "thumbs_up": "1",
                    "comment": "",
                    "csrf_token": csrf_token,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["feedback_id"], 42)
        save_mock.assert_awaited_once_with(
            session_id="feedback-1",
            question="Dieu kien tot nghiep la gi?",
            answer="Can du tin chi theo quy dinh.",
            thumbs_up=True,
            comment="",
        )

    def test_chat_sources_are_hidden_for_user_and_kept_for_admin(self) -> None:
        chat_result = {
            "response": "Can du dieu kien tot nghiep.",
            "sources": ["student_handbooks/2025.md"],
            "source_details": [
                {
                    "source": "student_handbooks/2025.md",
                    "label": "So tay sinh vien 2025",
                }
            ],
        }

        with patch("controllers.web_controller.process_chat_message", AsyncMock(return_value=chat_result)):
            user_client = TestClient(main.app)
            _login_as_user(user_client)
            user_response = user_client.post(
                "/chat",
                data={
                    "message": "Dieu kien tot nghiep?",
                    "session_id": "source-user",
                    "csrf_token": _csrf_from_chat_page(user_client),
                },
            )

            admin_client = TestClient(main.app)
            _login_as_admin(admin_client)
            admin_response = admin_client.post(
                "/chat",
                data={
                    "message": "Dieu kien tot nghiep?",
                    "session_id": "source-admin",
                    "csrf_token": _csrf_from_chat_page(admin_client),
                },
            )

        self.assertNotIn("sources", user_response.json())
        self.assertNotIn("source_details", user_response.json())
        self.assertEqual(admin_response.json()["sources"], ["student_handbooks/2025.md"])
        self.assertEqual(admin_response.json()["source_details"], chat_result["source_details"])

    def test_source_preview_requires_login_and_renders_vector_chunks(self) -> None:
        anonymous = TestClient(main.app)
        anonymous_response = anonymous.get(
            "/source-preview?source=student_handbooks/2025.md",
            follow_redirects=False,
        )
        self.assertEqual(anonymous_response.status_code, 303)
        self.assertIn("/login", anonymous_response.headers["location"])

        user_client = TestClient(main.app)
        _login_as_user(user_client)
        user_response = user_client.get(
            "/source-preview?source=student_handbooks/2025.md",
            follow_redirects=False,
        )
        self.assertEqual(user_response.status_code, 303)
        self.assertEqual(user_response.headers["location"], "/chat")

        client = TestClient(main.app)
        _login_as_admin(client)
        with patch(
            "controllers.web_controller.fetch_documents_by_source",
            return_value=(["Noi dung hoc vu <b>can escape</b>"], [{"source": "student_handbooks/2025.md"}]),
        ):
            response = client.get("/source-preview?source=student_handbooks/2025.md")

        self.assertEqual(response.status_code, 200)
        self.assertIn("student_handbooks/2025.md", response.text)
        self.assertIn("Noi dung hoc vu", response.text)
        self.assertIn("&lt;b&gt;can escape&lt;/b&gt;", response.text)

    def test_source_preview_uses_friendly_handbook_question_title(self) -> None:
        client = TestClient(main.app)
        _login_as_admin(client)
        source = "student_handbooks/5. SO TAY SINH VIEN 2022-2023.questions.md"

        with patch(
            "controllers.web_controller.fetch_documents_by_source",
            return_value=(["Noi dung hoc vu"], [{"source": source}]),
        ):
            response = client.get(f"/source-preview?source={source}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Sổ tay sinh viên 2022-2023 (hỏi đáp trích xuất)", response.text)
        self.assertIn(source, response.text)

    def test_source_preview_returns_404_when_source_missing(self) -> None:
        client = TestClient(main.app)
        _login_as_admin(client)
        with patch("controllers.web_controller.fetch_documents_by_source", return_value=([], [])):
            response = client.get("/source-preview?source=missing.md")

        self.assertEqual(response.status_code, 404)

    def test_chat_page_shows_source_support_only_when_admin_response_contains_sources(self) -> None:
        user_client = TestClient(main.app)
        _login_as_user(user_client)
        user_response = user_client.get("/chat")

        self.assertEqual(user_response.status_code, 200)
        self.assertIn("const CAN_VIEW_CHAT_SOURCES = false", user_response.text)

        client = TestClient(main.app)
        _login_as_admin(client)

        response = client.get("/chat")

        self.assertEqual(response.status_code, 200)
        self.assertIn("const CAN_VIEW_CHAT_SOURCES = true", response.text)
        self.assertIn("function renderSourceItem", response.text)
        self.assertIn("function formatSourceLabel", response.text)
        self.assertIn("source_details: data.source_details", response.text)
        self.assertIn("/source-preview?source=", response.text)

    def test_chat_page_starts_clean_and_shows_suggestions(self) -> None:
        client = TestClient(main.app)
        _login_as_user(client)

        response = client.get("/chat")

        self.assertEqual(response.status_code, 200)
        self.assertIn("resetChatOnPageLoad", response.text)
        self.assertNotIn("localStorage.setItem(LEGACY_CHAT_STATE_KEY", response.text)
        self.assertNotIn("localStorage.setItem(LEGACY_CHAT_ACTIVE_KEY", response.text)
        self.assertIn("Điều kiện tốt nghiệp là gì?", response.text)
        self.assertIn("Học lại có được cải thiện điểm không?", response.text)
        self.assertIn("Cuộc trò chuyện mới", response.text)
        self.assertIn("Lịch sử của tôi", response.text)
        self.assertNotIn("Thông báo Telegram", response.text)
        self.assertNotIn("telegramNoticeButton", response.text)
        self.assertNotIn("Dashboard đánh giá", response.text)

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
        self.assertEqual(mock_chat.await_args_list[0].kwargs["owner_username"], settings.USER_USERNAME)
        self.assertEqual(mock_chat.await_args_list[0].kwargs["owner_role"], "user")


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
