import unittest
from unittest import mock

from fastapi.testclient import TestClient

from main import app


class ApiResilienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_page_routes_render_successfully(self):
        for path in ("/", "/chat", "/upload", "/vector", "/config", "/history"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)

    def test_upload_page_mentions_markdown_support(self):
        response = self.client.get("/upload")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Markdown (.md)", response.text)

    def test_vector_status_endpoint_stays_available(self):
        response = self.client.get("/api/vector/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("routes", payload)
        self.assertIn("jobs", payload)

    def test_chat_endpoint_returns_503_when_chat_dependency_is_missing(self):
        missing_dependency = ModuleNotFoundError("No module named 'langchain'")
        missing_dependency.name = "langchain"

        with mock.patch(
            "app.services.chat_service.process_chat_message",
            side_effect=missing_dependency,
        ):
            response = self.client.post("/api/chat", json={"message": "Xin chao"})

        self.assertEqual(response.status_code, 503)
        self.assertIn("langchain", response.json()["detail"])

    def test_legacy_chat_post_alias_is_not_exposed(self):
        response = self.client.post("/chat", json={"message": "Xin chao"})

        self.assertEqual(response.status_code, 405)

    def test_legacy_chat_ui_alias_is_not_exposed(self):
        response = self.client.get("/chat-ui")

        self.assertEqual(response.status_code, 404)

    def test_rebuild_endpoint_returns_503_when_pipeline_is_unavailable(self):
        with mock.patch(
            "app.services.knowledge_base_service.start_rebuild_job",
            side_effect=RuntimeError("Knowledge pipeline chua san sang."),
        ):
            response = self.client.post("/api/vector/rebuild")

        self.assertEqual(response.status_code, 503)
        self.assertIn("Knowledge pipeline", response.json()["detail"])

    def test_chat_endpoint_returns_safe_dev_detail_for_unexpected_errors(self):
        with mock.patch(
            "app.services.chat_service.process_chat_message",
            side_effect=RuntimeError("boom AIzaSyExampleLeakToken1234567890"),
        ):
            response = self.client.post("/api/chat", json={"message": "Xin chao"})

        self.assertEqual(response.status_code, 500)
        self.assertIn("Chi tiết dev:", response.json()["detail"])
        self.assertNotIn("AIzaSyExampleLeakToken1234567890", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
