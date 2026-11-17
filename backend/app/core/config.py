import os
from functools import lru_cache
from pathlib import Path
from typing import List, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "AI Hospital Patient Feedback System"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Security & JWT
    SECRET_KEY: str = "production-hospital-secret-key-super-secure-change-in-prod-xyz987"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours shift

    # Database
    DATABASE_URL: str = "sqlite:///./data/hospital_feedback.db"

    # CORS
    CORS_ORIGINS: Union[str, List[str]] = [
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "*",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return ["*"]

    # Storage & Audio
    AUDIO_STORAGE_DIR: str = str(Path(__file__).parent.parent.parent / "data" / "audio")
    AUDIO_RETENTION_POLICY: str = "keep"  # 'keep' or 'delete_after_processing'
    MAX_AUDIO_MB: int = 50

    # AI Configuration
    AI_PROVIDER: str = "mock"  # 'gemini', 'openai', 'mock'
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # Hospital Policy / Consent
    CONSENT_NOTICE_TEXT: str = (
        "This conversation will be recorded and processed for hospital feedback and quality improvement."
    )

    # Retention Cron / Scheduled Webhook Secret
    CRON_SECRET: str = os.getenv("CRON_SECRET", "hospital-retention-cron-secret-key-2026")

    # Server-Side Master Administrator Account
    MASTER_USERNAME: str = os.getenv("MASTER_USERNAME", "Apollo@123")
    MASTER_PASSWORD: str = os.getenv("MASTER_PASSWORD", "2321@Apollo")
    MASTER_DISPLAY_NAME: str = os.getenv("MASTER_DISPLAY_NAME", "Apollo Master Administrator")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
