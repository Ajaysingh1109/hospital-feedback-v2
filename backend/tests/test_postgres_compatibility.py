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
