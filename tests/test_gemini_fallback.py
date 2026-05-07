from __future__ import annotations

import unittest
from unittest.mock import patch

from services.llm.gemini_service import (
    FALLBACK_MODEL_NAME,
    PRIMARY_MODEL_NAME,
    generate_content_with_fallback,
)


class _FakeModel:
    def __init__(self, response=None, exc: Exception | None = None) -> None:
        self.response = response
        self.exc = exc
        self.calls = 0

    def generate_content(self, *args, **kwargs):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return self.response


class GeminiFallbackTests(unittest.TestCase):
    def test_retries_with_flash_lite_on_quota_400(self) -> None:
        flash_model = _FakeModel(
            exc=RuntimeError('400 free tier quota exceeded for gemini-2.5-flash')
        )
        lite_response = object()
        lite_model = _FakeModel(response=lite_response)

        def fake_get_model(model_name: str = PRIMARY_MODEL_NAME):
            if model_name == PRIMARY_MODEL_NAME:
                return flash_model
            if model_name == FALLBACK_MODEL_NAME:
                return lite_model
            return None

        with patch('services.llm.gemini_service.get_model', side_effect=fake_get_model):
            response, used_model = generate_content_with_fallback('hello')

        self.assertIs(response, lite_response)
        self.assertEqual(used_model, FALLBACK_MODEL_NAME)
        self.assertEqual(flash_model.calls, 1)
        self.assertEqual(lite_model.calls, 1)

    def test_does_not_fallback_for_unrelated_400_errors(self) -> None:
        flash_model = _FakeModel(exc=RuntimeError('400 invalid argument'))
        lite_model = _FakeModel(response=object())

        def fake_get_model(model_name: str = PRIMARY_MODEL_NAME):
            if model_name == PRIMARY_MODEL_NAME:
                return flash_model
            if model_name == FALLBACK_MODEL_NAME:
                return lite_model
            return None

        with patch('services.llm.gemini_service.get_model', side_effect=fake_get_model):
            with self.assertRaisesRegex(RuntimeError, 'invalid argument'):
                generate_content_with_fallback('hello')

        self.assertEqual(flash_model.calls, 1)
        self.assertEqual(lite_model.calls, 0)


if __name__ == '__main__':
    unittest.main()

