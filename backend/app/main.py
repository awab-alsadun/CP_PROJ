"""
Application entrypoint.
uvicorn app.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager
import logging
import logging.handlers
import os
from pathlib import Path
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.supabase import get_supabase
from app.core.exceptions import AppError, NotFoundError, DatabaseError, ValidationError
from app.routers import (
    invoices,
    vendors,
    clients,
    upload,
    query,
    documents,
    analytics,
    notifications,
    payments,
    settings as settings_router,
    admin,
)


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def configure_logging() -> None:
    """
    Configure root logger to write to both stdout and a rotating file.

    backend/logs/backend.log — 10 MB per file, 5 backups kept.
    Format: "YYYY-MM-DD HH:MM:SS,mmm LEVEL logger_name message"

    invoice_processor is set to DEBUG for detailed pipeline tracing.
    All other loggers stay at INFO.
    """
    LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE = LOG_DIR / "backend.log"

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    # Stdout handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    stream_handler.setLevel(logging.INFO)

    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(LOG_FILE),
        maxBytes=10 * 1024 * 1024,   # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)

    # Root logger
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)   # handlers filter; root must be lowest
    root.addHandler(stream_handler)
    root.addHandler(file_handler)

    # Quiet noisy third-party loggers
    for noisy in ("httpx", "httpcore", "hpack", "openai", "supabase", "postgrest"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # DEBUG for invoice ingestion pipeline only
    logging.getLogger("app.services.invoice_processor").setLevel(logging.DEBUG)

    logging.getLogger(__name__).info(
        f"Logging configured — file: {LOG_FILE}"
    )


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log = logging.getLogger(__name__)

    # Supabase startup check
    db = get_supabase()
    db.table("companies").select("id").limit(1).execute()
    log.info("Supabase connection verified at startup")
    log.info("Storage active bucket: invoices")

    # Scheduler
    scheduler = BackgroundScheduler()

    def _run_overdue_check():
        from app.services.overdue_service import check_and_mark_overdue
        log.info(f"[overdue_check] starting scheduled run at {datetime.utcnow()}")
        try:
            db = get_supabase()
            companies = db.table("companies").select("id").execute()
            total = 0
            for c in (companies.data or []):
                result = check_and_mark_overdue(db, c["id"])
                count = result.get("overdue_count", 0)
                log.info(f"[overdue_check] flipped {count} invoices for company {c['id']}")
                total += count
            log.info(f"[overdue_check] complete: {total} total")
        except Exception as e:
            log.error(f"[overdue_check] scheduled run failed: {e}")

    scheduler.add_job(_run_overdue_check, "cron", hour=0, minute=0)
    scheduler.start()
    log.info("[overdue_check] scheduler started — job runs daily at 00:00")

    yield

    scheduler.shutdown(wait=False)
    log.info("[overdue_check] scheduler stopped")


settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"error": exc.message})


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError):
    return JSONResponse(status_code=400, content={"error": exc.message})


@app.exception_handler(DatabaseError)
async def database_error_handler(request: Request, exc: DatabaseError):
    return JSONResponse(
        status_code=502,
        content={"error": exc.message, "detail": exc.detail},
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=500, content={"error": exc.message})


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(invoices.router,        prefix=settings.API_V1_PREFIX)
app.include_router(vendors.router,         prefix=settings.API_V1_PREFIX)
app.include_router(clients.router,         prefix=settings.API_V1_PREFIX)
app.include_router(upload.router,          prefix=settings.API_V1_PREFIX)
app.include_router(query.router,           prefix=settings.API_V1_PREFIX)
app.include_router(documents.router,       prefix=settings.API_V1_PREFIX)
app.include_router(analytics.router,       prefix=settings.API_V1_PREFIX)
app.include_router(notifications.router,   prefix=settings.API_V1_PREFIX)
app.include_router(payments.router,        prefix=settings.API_V1_PREFIX)
app.include_router(settings_router.router, prefix=settings.API_V1_PREFIX)
app.include_router(admin.router,           prefix=settings.API_V1_PREFIX)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
def health_check():
    try:
        db = get_supabase()
        db.table("companies").select("id").limit(1).execute()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "status":   "ok" if db_status == "connected" else "degraded",
        "database": db_status,
    }