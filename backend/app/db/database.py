import logging
import os
import urllib.parse
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from ..core.config import get_settings

logger = logging.getLogger("hospital_feedback.db")
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
        env = os.getenv("ENVIRONMENT", "").strip().lower()
        is_cloud = (
            os.getenv("RENDER") == "true"
            or os.getenv("RENDER_SERVICE_NAME") is not None
            or os.getenv("KOYEB_APP_NAME") is not None
            or os.getenv("KOYEB_SERVICE_NAME") is not None
            or os.getenv("KOYEB_PUBLIC_DOMAIN") is not None
        )
        if env == "production" or is_cloud:
            return ""
        return "sqlite:///./data/hospital_feedback.db"

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


def get_database_diagnostics() -> dict:
    """
    Returns masked, security-safe database configuration and connectivity metadata.
    Never exposes passwords, tokens, or credentials.
    """
    db_keys = [
        "DATABASE_URL",
        "POSTGRES_URL",
        "SUPABASE_DB_URL",
        "SUPABASE_DATABASE_URL",
        "DB_URL",
        "DATABASE_EXTERNAL_URL",
        "DATABASE_INTERNAL_URL",
    ]
    env_summary = {}
    for k in db_keys:
        val = os.getenv(k, "").strip()
        if val:
            # Report presence and length without exposing content
            env_summary[k] = {
                "present": True,
                "length": len(val),
                "starts_with": val.split("://")[0] + "://" if "://" in val else val[:4],
                "contains_at_symbol": "@" in val,
            }
        else:
            env_summary[k] = {"present": False}

    if not db_url:
        return {
            "configured": False,
            "dialect": "none",
            "message": "No valid PostgreSQL database connection string found in environment variables.",
            "env_variables_detected": env_summary,
        }

    if db_url.startswith("sqlite"):
        return {
            "configured": True,
            "dialect": "sqlite",
            "is_remote": False,
            "path": db_url,
            "env_variables_detected": env_summary,
        }

    try:
        u = make_url(db_url)
        return {
            "configured": True,
            "dialect": u.drivername,
            "is_remote": True,
            "host": u.host,
            "port": u.port,
            "database": u.database,
            "username": u.username,
            "sslmode": u.query.get("sslmode", None),
            "env_variables_detected": env_summary,
        }
    except Exception as e:
        return {
            "configured": False,
            "dialect": "unknown",
            "error": str(e),
            "env_variables_detected": env_summary,
        }


db_url = normalize_database_url(settings.DATABASE_URL)

if not db_url:
    # If unconfigured in production, initialize in-memory SQLite engine so app can boot and report 503
    engine = create_engine("sqlite:///:memory:", future=True)
elif db_url.startswith("sqlite"):
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
        pool_recycle=300,
        pool_size=10,
        max_overflow=20,
        future=True,
    )


def fallback_to_sqlite() -> str:
    """
    Emergency runtime recovery: dynamically rebinds SQLAlchemy engine and SessionLocal
    to persistent local SQLite if the cloud database is down, invalid, or unresolvable.
    Prevents Render / cloud container crashes and ensures 100% service uptime.
    """
    global engine, db_url
    fallback_url = "sqlite:///./data/hospital_feedback.db"
    parsed_path = fallback_url.replace("sqlite:///", "")
    full_path = Path(parsed_path).resolve()
    full_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        engine.dispose()
    except Exception:
        pass

    engine = create_engine(
        fallback_url,
        echo=False,
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal.configure(bind=engine)
    db_url = fallback_url
    logger.info("[DATABASE RECOVERY] Successfully switched database engine to persistent SQLite.")
    return fallback_url


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
