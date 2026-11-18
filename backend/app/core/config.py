import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "FEEDBACK MAC"
    BRAND_LINE: str = "Powered by Saarthi-One"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Security & JWT
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours shift

    @field_validator("SECRET_KEY", mode="before")
    @classmethod
    def validate_secret_key(cls, v: Optional[str]) -> str:
        val = (v or os.getenv("SECRET_KEY", "")).strip()
        env = os.getenv("ENVIRONMENT", "development").lower()
        if env == "production":
            if not val or val == "production-hospital-secret-key-super-secure-change-in-prod-xyz987":
                raise ValueError(
                    "CRITICAL SECURITY CONFIGURATION ERROR: SECRET_KEY environment variable is missing in production! "
                    "A secure 32+ character random secret key must be set via environment variable or .env, "
                    "and cannot default to static codebase keys."
                )
        if not val:
            return "dev-insecure-test-secret-key-for-local-development-only-32chars"
        return val

    # Database
    DATABASE_URL: str = "sqlite:///./data/hospital_feedback.db"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def resolve_database_url(cls, v: Optional[str]) -> str:
        for key in ["DATABASE_URL", "POSTGRES_URL", "SUPABASE_DB_URL", "DATABASE_INTERNAL_URL", "DATABASE_EXTERNAL_URL"]:
            val = os.getenv(key, "").strip()
            if val:
                return val
        if v and v != "sqlite:///./data/hospital_feedback.db":
            return v.strip()
        return "sqlite:///./data/hospital_feedback.db"

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
    AI_PROVIDER: str = "gemini"  # 'gemini', 'openai', 'mock'
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    OPENAI_API_KEY: str = ""

    @field_validator("GEMINI_API_KEY", mode="before")
    @classmethod
    def resolve_gemini_api_key(cls, v: Optional[str]) -> str:
        if v and v.strip():
            return v.strip()
        env_val = os.getenv("GEMINI_API_KEY", "").strip()
        if env_val:
            return env_val
        # Check parent workspace .env as fallback
        root_env = Path(__file__).parent.parent.parent.parent / ".env"
        if root_env.exists():
            for line in root_env.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("GEMINI_API_KEY="):
                    val = line.split("=", 1)[1].strip()
                    if val:
                        return val
        return ""

    @field_validator("GEMINI_MODEL", mode="before")
    @classmethod
    def resolve_gemini_model(cls, v: Optional[str]) -> str:
        if v and v.strip():
            return v.strip()
        return os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

    # Hospital Policy / Consent
    CONSENT_NOTICE_TEXT: str = (
        "This conversation will be recorded and processed for hospital feedback and quality improvement."
    )

    # Retention Cron / Scheduled Webhook Secret
    CRON_SECRET: str = ""

    @field_validator("CRON_SECRET", mode="before")
    @classmethod
    def validate_cron_secret(cls, v: Optional[str]) -> str:
        val = (v or os.getenv("CRON_SECRET", "")).strip()
        env = os.getenv("ENVIRONMENT", "development").lower()
        if env == "production":
            if not val or val == "hospital-retention-cron-secret-key-2026":
                raise ValueError(
                    "CRITICAL SECURITY CONFIGURATION ERROR: CRON_SECRET environment variable is missing in production! "
                    "A secure secret token must be set via environment variable or .env."
                )
        if not val:
            return "dev-cron-secret-for-local-testing-only"
        return val

    # Server-Side Master Administrator Account
    MASTER_USERNAME: str = os.getenv("MASTER_USERNAME", "")
    MASTER_PASSWORD: str = os.getenv("MASTER_PASSWORD", "")
    MASTER_DISPLAY_NAME: str = os.getenv("MASTER_DISPLAY_NAME", "Hospital Master Administrator")

    @field_validator("MASTER_PASSWORD", mode="before")
    @classmethod
    def validate_master_password(cls, v: Optional[str]) -> str:
        # Must come strictly from environment variable or .env file (NEVER hardcoded defaults)
        val = (v or os.getenv("MASTER_PASSWORD", "")).strip()
        if not val:
            raise ValueError(
                "CRITICAL SECURITY CONFIGURATION ERROR: MASTER_PASSWORD environment variable is missing! "
                "The master administrator password must be explicitly set via environment variable or .env, "
                "and cannot default to hardcoded credentials."
            )
        return val

    @field_validator("MASTER_USERNAME", mode="before")
    @classmethod
    def validate_master_username(cls, v: Optional[str]) -> str:
        val = (v or os.getenv("MASTER_USERNAME", "")).strip()
        if not val:
            raise ValueError(
                "CRITICAL SECURITY CONFIGURATION ERROR: MASTER_USERNAME environment variable is missing! "
                "The master administrator username must be explicitly set via environment variable or .env."
            )
        return val

    # Server-Side Employee / Feedback User Account (Section 2, 3)
    FEEDBACK_USER_USERNAME: str = os.getenv("FEEDBACK_USER_USERNAME", "")
    FEEDBACK_USER_PASSWORD: str = os.getenv("FEEDBACK_USER_PASSWORD", "")
    FEEDBACK_USER_DISPLAY_NAME: str = os.getenv("FEEDBACK_USER_DISPLAY_NAME", "Duty Feedback Nurse")

    @field_validator("FEEDBACK_USER_PASSWORD", mode="before")
    @classmethod
    def validate_feedback_user_password(cls, v: Optional[str]) -> str:
        return (v or os.getenv("FEEDBACK_USER_PASSWORD", "")).strip()


@lru_cache()
def get_settings() -> Settings:
    return Settings()
