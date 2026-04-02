import builtins
import importlib
import os
import sys
import unittest
from contextlib import contextmanager
from unittest import mock


CONFIG_MODULE = "app.core.config"
CORE_MODULE = "app.core"
ENV_KEYS = {
    "APP_DEBUG",
    "APP_ENV",
    "FLASK_DEBUG",
    "FLASK_SECRET_KEY",
    "GEMINI_API_KEY",
    "LLM_PROVIDER",
    "SECRET_KEY",
}


@contextmanager
def load_config_with_env(overrides):
    previous_env = {key: os.environ.get(key) for key in ENV_KEYS}
    previous_modules = {
        CONFIG_MODULE: sys.modules.get(CONFIG_MODULE),
        CORE_MODULE: sys.modules.get(CORE_MODULE),
    }
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "dotenv":
            raise ImportError("missing dotenv")
        return original_import(name, globals, locals, fromlist, level)

    try:
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        os.environ.update(overrides)
        sys.modules.pop(CONFIG_MODULE, None)
        sys.modules.pop(CORE_MODULE, None)
        with mock.patch("builtins.__import__", side_effect=fake_import):
            module = importlib.import_module(CONFIG_MODULE)
        yield module
    finally:
        sys.modules.pop(CONFIG_MODULE, None)
        sys.modules.pop(CORE_MODULE, None)
        for name, module in previous_modules.items():
            if module is not None:
                sys.modules[name] = module
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class ConfigEnvTests(unittest.TestCase):
    def test_config_reads_new_env_names(self):
        with load_config_with_env(
            {
                "APP_DEBUG": "0",
                "APP_ENV": "development",
                "SECRET_KEY": "new-secret",
            }
        ) as config:
            self.assertFalse(config.APP_DEBUG)
            self.assertEqual(config.SECRET_KEY, "new-secret")

    def test_flask_debug_is_no_longer_used(self):
        with load_config_with_env({"FLASK_DEBUG": "0"}) as config:
            self.assertTrue(config.APP_DEBUG)

    def test_flask_secret_key_is_no_longer_accepted_in_production(self):
        with self.assertRaises(RuntimeError):
            with load_config_with_env(
                {
                    "APP_ENV": "production",
                    "SECRET_KEY": "",
                    "FLASK_SECRET_KEY": "legacy-secret",
                }
            ):
                pass

    def test_auto_provider_uses_gemini_when_key_exists(self):
        with load_config_with_env(
            {
                "LLM_PROVIDER": "auto",
                "GEMINI_API_KEY": "configured-key",
            }
        ) as config:
            self.assertEqual(config.ACTIVE_LLM_PROVIDER, "gemini")

    def test_auto_provider_falls_back_to_ollama_without_gemini_key(self):
        with load_config_with_env({"LLM_PROVIDER": "auto"}) as config:
            self.assertEqual(config.ACTIVE_LLM_PROVIDER, "ollama")


if __name__ == "__main__":
    unittest.main()
