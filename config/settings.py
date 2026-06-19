from __future__ import annotations

import os
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    APP_NAME: str = Field(
        default="ICTU AI Chatbot",
        validation_alias=AliasChoices("APP_NAME"),
    )
    ENVIRONMENT: str = Field(
        default="development",
        validation_alias=AliasChoices("ENVIRONMENT", "APP_ENV", "ENV"),
    )
    GEMINI_API_KEY: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_API_KEY"),
    )
    PARTNER_API_KEY: str = Field(
        default="dev-partner-key",
        validation_alias=AliasChoices("PARTNER_API_KEY"),
    )
    JWT_SECRET: str = Field(
        default="dev-jwt-secret",
        validation_alias=AliasChoices("JWT_SECRET", "SECRET_KEY"),
    )
    SESSION_SECRET: str = Field(
        default="",
        validation_alias=AliasChoices("SESSION_SECRET", "SESSION_MIDDLEWARE_SECRET"),
    )
    ADMIN_USERNAME: str = Field(
        default="admin@gmail.com",
        validation_alias=AliasChoices("ADMIN_USERNAME"),
    )
    ADMIN_PASSWORD: str = Field(
        default="123456",
        validation_alias=AliasChoices("ADMIN_PASSWORD"),
    )
    ADMIN_ROLE: str = Field(
        default="admin",
        validation_alias=AliasChoices("ADMIN_ROLE"),
    )
    USER_USERNAME: str = Field(
        default="student",
        validation_alias=AliasChoices("USER_USERNAME", "STUDENT_USERNAME"),
    )
    USER_PASSWORD: str = Field(
        default="123456",
        validation_alias=AliasChoices("USER_PASSWORD", "STUDENT_PASSWORD"),
    )
    USER_ROLE: str = Field(
        default="user",
        validation_alias=AliasChoices("USER_ROLE", "STUDENT_ROLE"),
    )
    CORS_ALLOW_ORIGINS: str = Field(
        default="http://127.0.0.1:8000,http://localhost:8000",
        validation_alias=AliasChoices("CORS_ALLOW_ORIGINS", "ALLOWED_ORIGINS"),
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True,
        validation_alias=AliasChoices("CORS_ALLOW_CREDENTIALS"),
    )

    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    RAG_FUSION_METHOD: str = Field(
        default="rrf",
        validation_alias=AliasChoices("RAG_FUSION_METHOD", "FUSION_METHOD"),
    )
    RRF_K: int = Field(default=60, ge=1, validation_alias=AliasChoices("RRF_K"))
    HYBRID_ALPHA: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices("HYBRID_ALPHA"),
    )
    AUTO_APPROVE_CHAT_QA: bool = Field(
        default=False,
        validation_alias=AliasChoices("AUTO_APPROVE_CHAT_QA"),
    )
    SEARXNG_URL: str = Field(
        default="",
        validation_alias=AliasChoices("SEARXNG_URL", "SEARXNG_API", "SEAXNG_API"),
    )
    TRAFILATURA_URL: str = Field(
        default="",
        validation_alias=AliasChoices("TRAFILATURA_URL", "TRAFILATURA_API"),
    )

    API_RATE_CHAT: str = "100/minute"
    API_RATE_UPLOAD: str = "10/hour"
    API_RATE_ADMIN: str = "10/minute"
    API_RATE_TOKEN: str = "20/minute"

    MAX_CHAT_MESSAGE_CHARS: int = 2000
    MAX_CHAT_SESSION_ID_CHARS: int = 128
    CHAT_MEMORY_TTL_SECONDS: int = 30 * 24 * 60 * 60
    CHAT_MEMORY_MAX_MESSAGES: int = 40
    CHAT_MEMORY_MAX_SESSIONS: int = 4096
    SHOW_LEGACY_UNOWNED_CHAT_HISTORY_TO_USERS: bool = Field(
        default=True,
        validation_alias=AliasChoices("SHOW_LEGACY_UNOWNED_CHAT_HISTORY_TO_USERS"),
    )
    MAX_UPLOAD_FILES: int = 20
    MAX_UPLOAD_FILE_SIZE_BYTES: int = 10 * 1024 * 1024
    MAX_UPLOAD_BATCH_SIZE_BYTES: int = 50 * 1024 * 1024

    PROJECT_ROOT: Path = PROJECT_ROOT
    DATA_DIR: Path = Path("data")
    LOG_DIR: Path = Path("logs")
    FRONTEND_TEMPLATE_DIR: Path = Path("views/frontend/templates")
    FRONTEND_ASSET_DIR: Path = Path("views/frontend/assets")

    UPLOAD_DIR: Path = Path("data/uploads")
    RAG_UPLOAD_ROOT: Path = Path("data/rag_uploads")
    DB_PATH: Path = Path("data/bot_config.db")
    QA_CORPUS_ROOT: Path = Path("data/primary_corpus")
    VECTORSTORE_DIR: Path = Path("vectorstore")
    API_LOG_PATH: Path = Path("logs/api.log")
    SYSTEM_PROMPT_PATH: Path = Path("data/systemprompt.md")
    BOT_RULE_PATH: Path = Path("data/bot-rule.md")
    INTENTS_DIR: Path = Path("data/intents")
    BADWORDS_PATH: Path = Path("data/badwords.md")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def model_post_init(self, __context) -> None:  # type: ignore[override]
        root = Path(self.PROJECT_ROOT)
        if not root.is_absolute():
            root = (PROJECT_ROOT / root).resolve()
        else:
            root = root.resolve()
        self.PROJECT_ROOT = root

        for field_name in (
            "DATA_DIR",
            "LOG_DIR",
            "FRONTEND_TEMPLATE_DIR",
            "FRONTEND_ASSET_DIR",
            "UPLOAD_DIR",
            "RAG_UPLOAD_ROOT",
            "DB_PATH",
            "QA_CORPUS_ROOT",
            "VECTORSTORE_DIR",
            "API_LOG_PATH",
            "SYSTEM_PROMPT_PATH",
            "BOT_RULE_PATH",
            "INTENTS_DIR",
            "BADWORDS_PATH",
        ):
            path_value = Path(getattr(self, field_name))
            if not path_value.is_absolute():
                path_value = (self.PROJECT_ROOT / path_value).resolve()
            else:
                path_value = path_value.resolve()
            setattr(self, field_name, path_value)

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.strip().lower() in {"production", "prod"}

    @property
    def cors_allowed_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.CORS_ALLOW_ORIGINS.split(",")
            if origin.strip()
        ]


def _validate_production_security_config(settings_obj: Settings) -> None:
    if not settings_obj.is_production:
        return

    insecure_partner_key = settings_obj.PARTNER_API_KEY.strip() in {"", "dev-partner-key"}
    insecure_jwt_secret = settings_obj.JWT_SECRET.strip() in {"", "dev-jwt-secret"}
    insecure_session_secret = settings_obj.SESSION_SECRET.strip() in {"", "dev-jwt-secret"}
    insecure_admin_password = settings_obj.ADMIN_PASSWORD.strip() in {"", "admin", "123456"}
    insecure_user_password = settings_obj.USER_PASSWORD.strip() in {"", "user", "student", "123456"}

    if (
        insecure_partner_key
        or insecure_jwt_secret
        or insecure_session_secret
        or insecure_admin_password
        or insecure_user_password
    ):
        raise RuntimeError(
            "Production security config invalid: PARTNER_API_KEY/JWT_SECRET/SESSION_SECRET/"
            "ADMIN_PASSWORD/USER_PASSWORD "
            "must be set to non-default values."
        )

    origins = settings_obj.cors_allowed_origins
    if not origins:
        raise RuntimeError("Production security config invalid: CORS_ALLOW_ORIGINS must not be empty.")
    if "*" in origins:
        raise RuntimeError("Production security config invalid: wildcard CORS origin '*' is not allowed.")
    if any(
        origin.startswith("http://localhost")
        or origin.startswith("https://localhost")
        or "127.0.0.1" in origin
        for origin in origins
    ):
        raise RuntimeError(
            "Production security config invalid: localhost/127.0.0.1 origins are not allowed in production."
        )


def _is_azure_app_service() -> bool:
    return bool(os.getenv("WEBSITE_SITE_NAME") or os.getenv("WEBSITE_INSTANCE_ID"))


def _is_path_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return os.access(path, os.W_OK)


def _is_under_home_site(path: Path) -> bool:
    normalized = path.as_posix().rstrip("/")
    return normalized == "/home/site" or normalized.startswith("/home/site/")


def _bootstrap_azure_cache_dirs() -> None:
    if not _is_azure_app_service():
        return

    print("[CACHE] Bootstrapping Azure App Service paths (before embedding model load)...")

    # Cố gắng dùng thư mục persistent (/home/data) trước, nếu không được thì fallback sang /tmp
    cache_roots = [
        Path(os.getenv("AZURE_CACHE_ROOT", "/home/data")),
        Path("/tmp/azure_cache"),
    ]

    selected_root = None
    for root in cache_roots:
        try:
            root.mkdir(parents=True, exist_ok=True)
            test_file = root / ".test_write"
            test_file.touch()
            test_file.unlink()
            selected_root = root
            print(f"[CACHE] Using writable root: {selected_root}")
            break
        except OSError as exc:
            print(f"[CACHE] Cannot prepare cache root {root}: {exc}")
            continue

    if not selected_root:
        print("[CACHE] CRITICAL: No writable cache root found!")
        return

    cache_targets = {
        "HF_HOME": selected_root / "hf-cache",
        "HUGGINGFACE_HUB_CACHE": selected_root / "hf-cache" / "hub",
        "TRANSFORMERS_CACHE": selected_root / "transformers",
        "SENTENCE_TRANSFORMERS_HOME": selected_root / "sentence-transformers",
        "TORCH_HOME": selected_root / ".cache" / "torch",
        "XDG_CACHE_HOME": selected_root / ".cache",
    }

    for env_name, fallback_path in cache_targets.items():
        current_value = os.getenv(env_name, "").strip()
        current_path = Path(current_value) if current_value else None
        should_override = current_path is None
        if current_path is not None:
            should_override = _is_under_home_site(current_path) or not _is_path_writable(current_path)
        if not should_override:
            print(f"[CACHE] Keeping {env_name}={current_path}")
            continue

        try:
            fallback_path.mkdir(parents=True, exist_ok=True)
            os.environ[env_name] = str(fallback_path)
            print(f"[CACHE] {env_name} -> {fallback_path}")
        except OSError as exc:
            print(f"[CACHE] Cannot prepare {env_name} at {fallback_path}: {exc}")

    vectorstore_target = selected_root / "vectorstore"
    current_vectorstore = settings.VECTORSTORE_DIR
    should_override_vectorstore = (
        _is_under_home_site(current_vectorstore)
        or not _is_path_writable(current_vectorstore)
        or current_vectorstore.as_posix().startswith("/app/")
    )
    if should_override_vectorstore:
        try:
            vectorstore_target.mkdir(parents=True, exist_ok=True)
            settings.VECTORSTORE_DIR = vectorstore_target.resolve()
            os.environ["VECTORSTORE_DIR"] = str(settings.VECTORSTORE_DIR)
            print(f"[CACHE] VECTORSTORE_DIR -> {settings.VECTORSTORE_DIR}")
        except OSError as exc:
            print(f"[CACHE] Cannot prepare VECTORSTORE_DIR at {vectorstore_target}: {exc}")
    else:
        print(f"[CACHE] Keeping VECTORSTORE_DIR={current_vectorstore}")

    app_data_target = selected_root / "app"
    current_data_dir = settings.DATA_DIR
    should_override_app_data = (
        _is_under_home_site(current_data_dir)
        or not _is_path_writable(current_data_dir)
        or current_data_dir.as_posix().startswith("/app/")
    )
    if should_override_app_data:
        try:
            app_data_target.mkdir(parents=True, exist_ok=True)
            settings.DATA_DIR = app_data_target.resolve()
            os.environ["DATA_DIR"] = str(settings.DATA_DIR)
            settings.DB_PATH = (app_data_target / "bot_config.db").resolve()
            os.environ["DB_PATH"] = str(settings.DB_PATH)
            settings.RAG_UPLOAD_ROOT = (app_data_target / "rag_uploads").resolve()
            os.environ["RAG_UPLOAD_ROOT"] = str(settings.RAG_UPLOAD_ROOT)
            print(f"[CACHE] DATA_DIR -> {settings.DATA_DIR}")
            print(f"[CACHE] DB_PATH -> {settings.DB_PATH}")
            print(f"[CACHE] RAG_UPLOAD_ROOT -> {settings.RAG_UPLOAD_ROOT}")
        except OSError as exc:
            print(f"[CACHE] Cannot prepare app data dir at {app_data_target}: {exc}")

    print("[CACHE] Azure bootstrap complete. Final cache paths:")
    for env_name in cache_targets:
        print(f"[CACHE]   {env_name}={os.getenv(env_name, '(unset)')}")
    print(f"[CACHE]   VECTORSTORE_DIR={settings.VECTORSTORE_DIR}")


settings = Settings()
_validate_production_security_config(settings)
if not settings.SESSION_SECRET:
    settings.SESSION_SECRET = settings.JWT_SECRET

# Bootstrap Azure cache dirs TRƯỚC khi tạo thư mục khác,
# để các biến HF_HOME, TRANSFORMERS_CACHE, v.v. được set sớm
# cho tất cả code phía sau (embedding pipeline, vector store, ...)
_bootstrap_azure_cache_dirs()

settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.RAG_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
settings.QA_CORPUS_ROOT.mkdir(parents=True, exist_ok=True)
settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
settings.VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
settings.API_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
settings.SYSTEM_PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
settings.BOT_RULE_PATH.parent.mkdir(parents=True, exist_ok=True)
settings.INTENTS_DIR.mkdir(parents=True, exist_ok=True)
settings.BADWORDS_PATH.parent.mkdir(parents=True, exist_ok=True)

__all__ = ["Settings", "settings"]
