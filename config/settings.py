from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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

    API_RATE_CHAT: str = "100/minute"
    API_RATE_UPLOAD: str = "10/hour"
    API_RATE_ADMIN: str = "10/minute"

    UPLOAD_DIR: Path = Path("data/uploads")
    RAG_UPLOAD_ROOT: Path = Path("data/rag_uploads")
    DB_PATH: Path = Path("data/bot_config.db")
    QA_CORPUS_ROOT: Path = Path("data/qa_generated_fixed")
    LOG_DIR: Path = Path("logs")
    API_LOG_PATH: Path = Path("logs/api.log")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

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

    if insecure_partner_key or insecure_jwt_secret or insecure_session_secret:
        raise RuntimeError(
            "Production security config invalid: PARTNER_API_KEY/JWT_SECRET/SESSION_SECRET must be set "
            "to non-default values."
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


settings = Settings()
_validate_production_security_config(settings)
if not settings.SESSION_SECRET:
    settings.SESSION_SECRET = settings.JWT_SECRET
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.RAG_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
settings.QA_CORPUS_ROOT.mkdir(parents=True, exist_ok=True)
settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
settings.API_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

__all__ = ["Settings", "settings"]
