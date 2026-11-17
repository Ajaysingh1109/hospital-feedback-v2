import asyncio
import logging
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
from .services.retention_service import run_automatic_retention_purge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("hospital_feedback")

settings = get_settings()


async def scheduled_retention_worker():
    """Background task running automatic 48-hour retention purge periodically."""
    logger.info("[Retention Worker] Scheduled 48-hour retention worker started.")
    # Run once at startup to purge any expired records while server was offline
    try:
        with SessionLocal() as db:
            run_automatic_retention_purge(db=db, retention_hours=48)
    except Exception as e:
        logger.error(f"[Retention Worker] Startup purge exception: {e}")

    while True:
        try:
            # Check every 10 minutes (600 seconds)
            await asyncio.sleep(600)
            with SessionLocal() as db:
                run_automatic_retention_purge(db=db, retention_hours=48)
        except asyncio.CancelledError:
            logger.info("[Retention Worker] Retention worker cancelled during shutdown.")
            break
        except Exception as e:
            logger.error(f"[Retention Worker] Periodic purge loop error: {e}")
            await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Hospital Feedback System Database...")
    Base.metadata.create_all(bind=engine)
    # Ensure SQLite columns exist (migration for existing SQLite DBs; Postgres creates natively)
    if engine.dialect.name == "sqlite":
        from sqlalchemy import text
        try:
            with engine.connect() as conn:
                cols = [r[1] for r in conn.execute(text("PRAGMA table_info(feedback)")).fetchall()]
                if cols and "complaint" not in cols:
                    conn.execute(text("ALTER TABLE feedback ADD COLUMN complaint TEXT DEFAULT 'Not Provided'"))
                    conn.commit()
        except Exception as e:
            logger.warning(f"Column migration check notice: {e}")
    seed_database()
    logger.info("Database initialized and seeded.")

    # Start automated retention purge worker
    purge_task = asyncio.create_task(scheduled_retention_worker())

    yield

    purge_task.cancel()
    try:
        await purge_task
    except asyncio.CancelledError:
        pass
    logger.info("Shutting down Hospital Feedback System.")


app = FastAPI(
    title=settings.APP_NAME,
    description="Production-Ready AI Hospital Patient Feedback Platform",
    version="1.0.0",
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


from .services.ai.factory import get_active_ai_mode

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "ai_provider": settings.AI_PROVIDER,
        "ai_mode": get_active_ai_mode(),
    }


# Static Frontend Mount for Unified Single-Server Deployment
static_dir = Path(__file__).parent.parent.parent / "frontend" / "dist"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        index_file = static_dir / "index.html"
        if index_file.exists() and not request.url.path.startswith("/api"):
            return FileResponse(index_file)
        return JSONResponse(status_code=404, content={"detail": "Not found"})



if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
