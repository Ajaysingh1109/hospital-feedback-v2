import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .api.v1.router import api_router
from .core.config import get_settings
from .db.database import Base, SessionLocal, engine
from .seed import seed_database
from .services.recovery_service import recover_orphaned_feedback_jobs
from .services.retention_service import run_automatic_retention_purge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("hospital_feedback")

settings = get_settings()


async def scheduled_retention_worker():
    """Background task running automatic 12-hour retention purge periodically."""
    logger.info("[Retention Worker] Scheduled 12-hour retention worker started.")
    # Run once at startup to purge any expired records while server was offline
    try:
        with SessionLocal() as db:
            run_automatic_retention_purge(db=db, retention_hours=12)
    except Exception as e:
        logger.error(f"[Retention Worker] Startup purge exception: {e}")

    while True:
        try:
            # Check every 10 minutes (600 seconds)
            await asyncio.sleep(600)
            with SessionLocal() as db:
                run_automatic_retention_purge(db=db, retention_hours=12)
        except asyncio.CancelledError:
            logger.info("[Retention Worker] Retention worker cancelled during shutdown.")
            break
        except Exception as e:
            logger.error(f"[Retention Worker] Periodic purge loop error: {e}")
            await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Hospital Feedback System Database...")
    is_prod = (
        settings.ENVIRONMENT == "production"
        or os.getenv("RENDER") == "true"
        or os.getenv("KOYEB_APP_NAME") is not None
        or os.getenv("KOYEB_SERVICE_NAME") is not None
        or os.getenv("KOYEB_PUBLIC_DOMAIN") is not None
    )
    db_ready = False
    max_retries = 3
    from sqlalchemy import text

    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            Base.metadata.create_all(bind=engine)
            db_ready = True
            break
        except Exception as e:
            logger.warning(f"[Database Init Attempt {attempt}/{max_retries}] Notice: {e}")
            if attempt < max_retries:
                await asyncio.sleep(2)
            else:
                if is_prod:
                    logger.error(
                        f"[CRITICAL PRODUCTION DATABASE ERROR] Failed to connect to PostgreSQL: {e}. "
                        "Refusing to silently mask production database failure with SQLite."
                    )
                else:
                    logger.warning("Local development fallback to SQLite.")
                    from .db.database import fallback_to_sqlite
                    fallback_to_sqlite()
                    Base.metadata.create_all(bind=engine)
                    db_ready = True

    if db_ready:
        # Ensure SQLite columns exist (migration for existing SQLite DBs; Postgres creates natively)
        if engine.dialect.name == "sqlite":
            try:
                with engine.connect() as conn:
                    cols = [r[1] for r in conn.execute(text("PRAGMA table_info(feedback)")).fetchall()]
                    if cols and "complaint" not in cols:
                        conn.execute(text("ALTER TABLE feedback ADD COLUMN complaint TEXT DEFAULT 'Not Provided'"))
                        conn.commit()
                    if cols and "processing_error" not in cols:
                        conn.execute(text("ALTER TABLE feedback ADD COLUMN processing_error TEXT"))
                        conn.commit()
            except Exception as e:
                logger.warning(f"Column migration check notice: {e}")
        seed_database()
        logger.info(f"Database initialized and seeded on dialect: {engine.dialect.name}.")

        # Recover any interrupted or orphaned background feedback jobs from previous run
        try:
            with SessionLocal() as db:
                recover_orphaned_feedback_jobs(db=db, engine_bind=engine)
        except Exception as e:
            logger.error(f"[Startup Recovery] Exception during recovery check: {e}")

    # Start automated retention purge worker
    purge_task = asyncio.create_task(scheduled_retention_worker())

    yield

    purge_task.cancel()
    try:
        await purge_task
    except asyncio.CancelledError:
        pass
    logger.info("Shutting down FEEDBACK MAC System.")


app = FastAPI(
    title=settings.APP_NAME,
    description="FEEDBACK MAC — Autonomous Bedside Voice Feedback Platform Powered by Saarthi-One",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS configuration for mobile and admin web
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Router
app.include_router(api_router)


# Custom Validation Error Handler to match Section 20 requirements
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    messages = []
    for err in errors:
        loc = err.get("loc", [])
        field = loc[-1] if loc else "field"
        msg = err.get("msg", "")

        if "Value error, UHID is required" in msg or field == "uhid":
            messages.append("UHID is required.")
        elif "Value error, Patient Name is required" in msg or field == "patient_name":
            messages.append("Patient Name is required.")
        elif "Value error, Department is required" in msg or field == "department":
            messages.append("Department is required.")
        else:
            messages.append(f"{field}: {msg}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": messages, "error_type": "VALIDATION_FAILED"},
    )


from .db.database import get_database_diagnostics
from .services.ai.factory import get_active_ai_mode
from sqlalchemy import text

@app.get("/health")
def health_check():
    is_prod = (
        settings.ENVIRONMENT == "production"
        or os.getenv("RENDER") == "true"
        or os.getenv("KOYEB_APP_NAME") is not None
        or os.getenv("KOYEB_SERVICE_NAME") is not None
        or os.getenv("KOYEB_PUBLIC_DOMAIN") is not None
    )
    diag = get_database_diagnostics()
    db_status = "connected"
    db_error = None

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        db_status = "error"
        err_str = str(e)
        if "@" in err_str:
            err_str = err_str.split("@")[-1]
        db_error = f"{type(e).__name__}: {err_str}"

    # Strict production health verification:
    # 1. Database connection must be live and responsive
    # 2. In production, database dialect MUST be PostgreSQL (never SQLite)
    is_healthy = (db_status == "connected")
    if is_prod:
        if engine.dialect.name != "postgresql":
            is_healthy = False
            db_error = db_error or "Production environment requires PostgreSQL database dialect, but SQLite is active. Please configure DATABASE_URL in cloud dashboard."

    response_payload = {
        "status": "healthy" if is_healthy else "unhealthy",
        "app_name": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "database_dialect": engine.dialect.name,
        "database_status": db_status,
        "database_diagnostic": diag,
        "ai_provider": settings.AI_PROVIDER,
        "ai_mode": get_active_ai_mode(),
    }
    if db_error:
        response_payload["database_error"] = db_error

    status_code = 200 if is_healthy else 503
    return JSONResponse(status_code=status_code, content=response_payload)


# Static Frontend Mount for Unified Single-Server Deployment
static_dir_candidates = [
    Path(__file__).parent.parent.parent / "frontend" / "dist",
    Path(__file__).parent.parent / "frontend" / "dist",
    Path("/app/frontend/dist"),
    Path("./frontend/dist"),
]
static_dir = next((p for p in static_dir_candidates if p.exists() and (p / "index.html").exists()), None)
if static_dir:
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        index_file = static_dir / "index.html"
        if index_file.exists() and not request.url.path.startswith("/api") and not request.url.path.startswith("/health"):
            return FileResponse(index_file)
        detail = getattr(exc, "detail", "Not found")
        return JSONResponse(status_code=404, content={"detail": detail})



if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
