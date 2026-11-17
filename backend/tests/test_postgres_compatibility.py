import pytest
from sqlalchemy import create_mock_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db.database import Base
from app.models import (
    AuditLog,
    Consultant,
    Department,
    DepartmentSubcategory,
    Feedback,
    FeedbackAIAnalysis,
    FeedbackAudio,
    FeedbackCorrection,
    FeedbackTranscript,
    HODMapping,
    Scheme,
    SyncQueue,
    SystemSetting,
    User,
)


def test_postgresql_ddl_compilation_all_14_tables():
    """
    Section 7: Verify that all database operations and normalized tables
    compile cleanly to production-grade PostgreSQL DDL.
    """
    all_models = [
        User,
        Department,
        DepartmentSubcategory,
        HODMapping,
        Scheme,
        Consultant,
        Feedback,
        FeedbackTranscript,
        FeedbackAudio,
        FeedbackAIAnalysis,
        FeedbackCorrection,
        SyncQueue,
        AuditLog,
        SystemSetting,
    ]

    for model in all_models:
        table = model.__table__
        # Compile table creation statement using PostgreSQL dialect
        ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        
        assert f"CREATE TABLE {table.name}" in ddl, f"Failed to generate PostgreSQL DDL for {table.name}"
        assert len(ddl) > 20

        # Verify PostgreSQL-specific type mappings
        for col in table.columns:
            col_type = col.type.compile(dialect=postgresql.dialect())
            assert col_type != "", f"Column {col.name} in table {table.name} has invalid PostgreSQL type"

    print(f"Verified PostgreSQL DDL compilation for all {len(all_models)} normalized tables successfully.")


def test_postgresql_mock_execution():
    """
    Verifies that create_all against a PostgreSQL engine mock executes all statements
    without dialect compilation errors.
    """
    statements = []

    def mock_executor(sql, *multiparams, **params):
        statements.append(str(sql.compile(dialect=postgresql.dialect())))

    mock_pg_engine = create_mock_engine("postgresql://user:pass@localhost:5432/db", executor=mock_executor)
    Base.metadata.create_all(mock_pg_engine)

    assert len(statements) >= 14, f"Expected at least 14 DDL statements, got {len(statements)}"


def test_database_url_normalization_for_psycopg2():
    """
    Verifies that postgres:// and postgresql:// are explicitly normalized to postgresql+psycopg2://
    to prevent SQLAlchemy 2.0+ from falling back to psycopg v3 (ModuleNotFoundError: No module named 'psycopg').
    Verifies:
    - Passwords containing '@' or special characters do not corrupt the hostname (e.g. host 'po' error)
    - Quoted URLs are properly unquoted and sanitized
    - Supabase / pooler URLs automatically receive sslmode=require
    - SQLite URLs remain completely unaffected for local development.
    """
    from sqlalchemy.engine import make_url
    from app.db.database import normalize_database_url

    # 1. postgres:// (Legacy Heroku/Render scheme)
    assert normalize_database_url("postgres://user:secret@dpg-host:5432/hospital_db") == (
        "postgresql+psycopg2://user:secret@dpg-host:5432/hospital_db"
    )

    # 2. postgresql:// (Render fromDatabase connectionString / Supabase / Neon)
    assert normalize_database_url("postgresql://hospital_user:secret@dpg-host:5432/hospital_feedback") == (
        "postgresql+psycopg2://hospital_user:secret@dpg-host:5432/hospital_feedback"
    )

    # 3. Password containing '@' causing host parsing issues
    # Without fix, @ inside password splits incorrectly and results in host "po" or error.
    url_with_at = "postgresql://postgres.myproject:TestUser@Pass999@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
    norm_at = normalize_database_url(url_with_at)
    assert "TestUser%40Pass999" in norm_at
    assert "sslmode=require" in norm_at
    parsed_at = make_url(norm_at)
    assert parsed_at.host == "aws-0-ap-south-1.pooler.supabase.com"
    assert parsed_at.port == 5432
    assert parsed_at.username == "postgres.myproject"
    assert parsed_at.password == "TestUser@Pass999"

    # 4. Quoted DATABASE_URL from .env or Render dashboard
    quoted_url = '"postgresql://user:pass@aws-0.pooler.supabase.com:5432/db"'
    norm_quoted = normalize_database_url(quoted_url)
    assert not norm_quoted.startswith('"')
    assert norm_quoted.startswith("postgresql+psycopg2://")
    parsed_quoted = make_url(norm_quoted)
    assert parsed_quoted.host == "aws-0.pooler.supabase.com"

    # 5. Already explicit postgresql+psycopg2:// (unmodified driver)
    assert normalize_database_url("postgresql+psycopg2://user:secret@localhost:5432/db") == (
        "postgresql+psycopg2://user:secret@localhost:5432/db"
    )

    # 6. Local SQLite development (unmodified)
    assert normalize_database_url("sqlite:///./data/hospital_feedback.db") == (
        "sqlite:///./data/hospital_feedback.db"
    )
    assert normalize_database_url("sqlite:///:memory:") == "sqlite:///:memory:"

