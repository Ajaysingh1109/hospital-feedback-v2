import os
from unittest.mock import patch
from app.core.config import Settings
from app.db.database import normalize_database_url
from app.services.audio_service import _get_supabase_storage_config, upload_to_supabase_storage, fetch_from_supabase_storage, delete_from_supabase_storage


def test_koyeb_env_detection_disables_sqlite_fallback():
    """Verify that when KOYEB_APP_NAME or KOYEB_SERVICE_NAME is present, SQLite fallback is disabled in normalize_database_url."""
    with patch.dict(os.environ, {"KOYEB_APP_NAME": "hospital-feedback-app", "ENVIRONMENT": "development"}, clear=False):
        normalized = normalize_database_url("")
        assert normalized == "", "In Koyeb cloud environment, empty DATABASE_URL must not fallback to SQLite"


def test_koyeb_database_url_normalization():
    """Verify PostgreSQL connection strings are correctly normalized on Koyeb with psycopg2 and sslmode."""
    raw = "postgres://postgres.testref:pass%40123@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
    normalized = normalize_database_url(raw)
    assert normalized.startswith("postgresql+psycopg2://")
    assert "sslmode=require" in normalized
    assert "aws-0-us-east-1.pooler.supabase.com:5432" in normalized


def test_supabase_storage_config_resolution():
    """Verify private Supabase Storage config resolution from environment variables."""
    # When unset
    with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": "", "SUPABASE_KEY": ""}, clear=False):
        assert _get_supabase_storage_config() is None

    # When set
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://xyzcompany.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
        "SUPABASE_STORAGE_BUCKET": "custom-audio-bucket"
    }, clear=False):
        cfg = _get_supabase_storage_config()
        assert cfg is not None
        assert cfg[0] == "https://xyzcompany.supabase.co"
        assert cfg[1] == "test-service-key"
        assert cfg[2] == "custom-audio-bucket"


def test_supabase_storage_graceful_error_handling():
    """Verify storage functions fail gracefully without throwing exceptions when network/config is unavailable."""
    with patch.dict(os.environ, {"SUPABASE_URL": "https://nonexistent-domain.supabase.co", "SUPABASE_KEY": "fake-key"}, clear=False):
        # Should return False / None gracefully without raising uncaught exceptions
        assert upload_to_supabase_storage(b"dummy_bytes", "test.webm") is False
        assert fetch_from_supabase_storage("test.webm") is None
        assert delete_from_supabase_storage("test.webm") is False
