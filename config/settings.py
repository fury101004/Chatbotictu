from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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


settings = Settings()
if not settings.SESSION_SECRET:
    settings.SESSION_SECRET = settings.JWT_SECRET
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.RAG_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
settings.QA_CORPUS_ROOT.mkdir(parents=True, exist_ok=True)
settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
settings.API_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

__all__ = ["Settings", "settings"]
