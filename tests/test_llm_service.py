import unittest
from unittest import mock

import requests

from app.services import llm_service


def _success_response(text: str):
    response = mock.Mock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": text},
                    ]
                }
            }
        ]
    }
    return response


def _http_error_response(status_code: int, text: str):
    response = mock.Mock()
    response.status_code = status_code
    response.text = text
    response.json.return_value = {}
    error = requests.HTTPError(f"HTTP {status_code}")
    error.response = response
    response.raise_for_status.side_effect = error
    return response


class LlmServiceTests(unittest.TestCase):
    def tearDown(self):
        llm_service.get_llm.cache_clear()

    def test_get_llm_uses_gemini_when_provider_resolves_to_gemini(self):
        with mock.patch.object(
            llm_service, "resolve_llm_provider", return_value="gemini"
        ), mock.patch.object(
            llm_service, "_build_gemini_client", return_value="gemini-client"
        ) as gemini_builder, mock.patch.object(
            llm_service, "_build_ollama_client", return_value="ollama-client"
        ) as ollama_builder:
            client = llm_service.get_llm()

        self.assertEqual(client, "gemini-client")
        gemini_builder.assert_called_once_with()
        ollama_builder.assert_not_called()

    def test_requests_gemini_client_invokes_generate_content_endpoint(self):
        with mock.patch.object(llm_service, "GEMINI_API_KEY", "configured-key"), mock.patch.object(
            llm_service, "GEMINI_MODEL", "gemini-2.5-flash"
        ), mock.patch(
            "app.services.llm_service.requests.post",
            return_value=_success_response("Trả lời từ Gemini"),
        ) as post_mock:
            client = llm_service._RequestsGeminiClient()
            reply = client.invoke("Xin chào")

        self.assertEqual(reply, "Trả lời từ Gemini")
        post_mock.assert_called_once()
        first_url = post_mock.call_args.args[0]
        self.assertIn("models/gemini-2.5-flash:generateContent", first_url)

    def test_requests_gemini_client_falls_back_to_compatible_model(self):
        with mock.patch.object(llm_service, "GEMINI_API_KEY", "configured-key"), mock.patch.object(
            llm_service, "GEMINI_MODEL", "gemini-2.5-flash"
        ), mock.patch(
            "app.services.llm_service.requests.post",
            side_effect=[
                _http_error_response(404, "Requested model was not found."),
                _success_response("Trả lời từ fallback model"),
            ],
        ) as post_mock:
            client = llm_service._RequestsGeminiClient()
            reply = client.invoke("Xin chào")

        self.assertEqual(reply, "Trả lời từ fallback model")
        self.assertEqual(post_mock.call_count, 2)
        first_url = post_mock.call_args_list[0].args[0]
        second_url = post_mock.call_args_list[1].args[0]
        self.assertIn("models/gemini-2.5-flash:generateContent", first_url)
        self.assertIn("models/gemini-1.5-flash:generateContent", second_url)

    def test_requests_gemini_client_raises_sanitized_error_when_all_models_fail(self):
        with mock.patch.object(llm_service, "GEMINI_API_KEY", "configured-key"), mock.patch.object(
            llm_service, "GEMINI_MODEL", "gemini-2.5-flash"
        ), mock.patch(
            "app.services.llm_service.requests.post",
            side_effect=[
                _http_error_response(404, "Requested model was not found for key configured-key."),
                _http_error_response(404, "Fallback model unavailable for key configured-key."),
            ],
        ):
            client = llm_service._RequestsGeminiClient()

            with self.assertRaises(llm_service.LLMInvocationError) as context:
                client.invoke("Xin chào")

        error = context.exception
        self.assertEqual(error.provider, "gemini")
        self.assertEqual(error.status_code, 404)
        self.assertIn("gemini-2.5-flash", error.debug_summary())
        self.assertIn("gemini-1.5-flash", error.debug_summary())
        self.assertNotIn("configured-key", error.debug_summary())


if __name__ == "__main__":
    unittest.main()
