import os
import urllib.parse
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from ..core.config import get_settings

settings = get_settings()


def normalize_database_url(url: str) -> str:
    """
    Normalizes database URL for cloud providers (Render, Supabase, Neon, Railway).
    1. Strips any surrounding quotes, whitespace, or newlines.
    2. Ensures that PostgreSQL URLs explicitly use the psycopg2 driver (postgresql+psycopg2://)
       to prevent SQLAlchemy 2.0+ from falling back to psycopg v3 (ModuleNotFoundError: No module named 'psycopg').
    3. Handles unencoded special characters in passwords (especially '@', ':', '#', etc.)
       which otherwise cause host parsing failures like:
       `sqlalchemy.exc.OperationalError: could not translate host name "po" to address`
    4. Automatically ensures `sslmode=require` for Supabase / remote poolers if missing.
    5. Preserves SQLite URLs and explicit driver specifications.
    """
    if not url:
        return url

    clean_url = url.strip().strip('"\'')

    # Ensure explicit psycopg2 driver
    if clean_url.startswith("postgres://"):
        clean_url = "postgresql+psycopg2://" + clean_url[len("postgres://"):]
    elif clean_url.startswith("postgresql://") and not clean_url.startswith("postgresql+"):
        clean_url = "postgresql+psycopg2://" + clean_url[len("postgresql://"):]

    # For PostgreSQL / remote connections, safely isolate credentials and encode password
    if "://" in clean_url and not clean_url.startswith("sqlite"):
        try:
            proto, remainder = clean_url.split("://", 1)
            # Find credentials vs host: use rsplit('@', 1) because the last '@' separates credentials from host
            if "@" in remainder:
                auth_part, host_part = remainder.rsplit("@", 1)
                if ":" in auth_part:
                    user, raw_pass = auth_part.split(":", 1)
                    # Safely encode special characters (like '@', '#', '$') in password
                    unquoted_pass = urllib.parse.unquote(raw_pass)
                    encoded_pass = urllib.parse.quote(unquoted_pass, safe="")
                    clean_url = f"{proto}://{user}:{encoded_pass}@{host_part}"
        except Exception:
            pass

        # Supabase and transaction/session poolers require SSL
        if any(h in clean_url.lower() for h in ["supabase.co", "supabase.com", "pooler"]):
            if "sslmode=" not in clean_url:
                delimiter = "&" if "?" in clean_url else "?"
                clean_url = f"{clean_url}{delimiter}sslmode=require"

    return clean_url


db_url = normalize_database_url(settings.DATABASE_URL)

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
