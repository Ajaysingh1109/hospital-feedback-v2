import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from ..core.config import get_settings

settings = get_settings()

db_url = settings.DATABASE_URL
# Normalization for managed PostgreSQL cloud providers (Render, Supabase, Railway, Neon)
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

if db_url.startswith("sqlite"):
    # Ensure local directory exists for SQLite
    parsed_path = db_url.replace("sqlite:///", "")
    if "./" in parsed_path or not os.path.isabs(parsed_path):
        full_path = Path(parsed_path).resolve()
        full_path.parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False}
    engine = create_engine(
        db_url,
        echo=False,
        connect_args=connect_args,
        future=True,
    )
else:
    # Production Cloud PostgreSQL Engine with pooling & automatic reconnect (pool_pre_ping)
    engine = create_engine(
        db_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        future=True,
    )

# Enable foreign keys for SQLite
if db_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
