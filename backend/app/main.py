import logging
import asyncio
import socket
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.api.v1.routes_health import router as health_router
from app.api.v1.routes_auth import router as auth_router
from app.api.v1.routes_pipeline import router as pipeline_router
from app.api.v1.routes_realtime import router as realtime_router
from app.core.logging_config import setup_logging
from app.core.config import get_settings
from app.core.middleware import SecurityHeadersMiddleware, SimpleRateLimitMiddleware
from app.db.session import engine
from app.models import Base  # noqa: F401 - register models before create_all
from app.db.session import AsyncSessionLocal
from app.services.ingestion import ingest_construction, ingest_traffic

# Initialize logging FIRST, before any other imports that might log
setup_logging()

# Get logger after logging is configured
logger = logging.getLogger(__name__)

API_V1_PREFIX = "/api/v1"


async def test_database_connectivity() -> bool:
    """
    Test database connectivity on startup.
    Create tables if they do not exist (Option B: create_all for early development).
    """
    try:
        settings = get_settings()
        logger.info("Testing database connectivity...")

        try:
            parsed = urlparse(settings.database_url)
            host = parsed.hostname
            if host:
                infos = socket.getaddrinfo(host, parsed.port or 5432, proto=socket.IPPROTO_TCP)
                families = {i[0] for i in infos}
                if families == {socket.AF_INET6}:
                    logger.warning(
                        "Database hostname resolves to IPv6 only; if your network blocks IPv6, "
                        "use the Supabase pooler host (IPv4) for DATABASE_URL",
                        extra={"host": host},
                    )
        except Exception:
            # Best-effort diagnostics; don't block startup
            pass

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connectivity test passed")

        # Create tables if they do not exist (early development; use Alembic for production)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schema up to date")

        logger.info(f"Database URL: {settings.get_database_url_masked()}")
        return True
    except Exception as e:
        logger.warning(
            f"Database connectivity test failed: {e} | "
            f"Application will continue to start, but database operations may fail"
        )
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI app startup and shutdown events.
    
    - On startup: Test database connectivity (optional)
    - On shutdown: Clean up resources
    """
    # Startup
    logger.info("Application startup: Testing database connectivity...")
    db_ok = await test_database_connectivity()

    settings = get_settings()
    stop_event = asyncio.Event()
    task: asyncio.Task | None = None

    async def _loop():
        interval = max(0, int(settings.ingestion_interval_seconds))
        if interval <= 0:
            return
        logger.info("Background ingestion loop started", extra={"interval_seconds": interval})
        while not stop_event.is_set():
            try:
                async with AsyncSessionLocal() as db:
                    await ingest_traffic(db)
                async with AsyncSessionLocal() as db:
                    await ingest_construction(db)
            except Exception as e:
                logger.exception("Background ingestion loop error", extra={"error": str(e)})
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    if db_ok and settings.ingestion_enabled and int(settings.ingestion_interval_seconds) > 0:
        task = asyncio.create_task(_loop())
    
    yield
    
    # Shutdown
    stop_event.set()
    if task is not None:
        try:
            await task
        except Exception:
            pass
    logger.info("Application shutdown: Closing database connections...")
    await engine.dispose()
    logger.info("Database connections closed")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    This factory function sets up the app with all routers and middleware.
    Logging is already configured before this function is called.
    """
    logger.info("Creating FastAPI application...")
    
    app = FastAPI(
        title="MetroGuardian Backend",
        version="0.1.0",
        description="Backend API for MetroGuardian traffic & construction alerts.",
        lifespan=lifespan,
    )

    settings = get_settings()

    # Step 7: security headers + basic rate limit
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(SimpleRateLimitMiddleware)

    # Step 7: CORS (add last)
    origins = [o.strip() for o in settings.cors_allow_origins.split(",")] if settings.cors_allow_origins else ["*"]
    methods = (
        ["*"]
        if settings.cors_allow_methods.strip() == "*"
        else [m.strip() for m in settings.cors_allow_methods.split(",") if m.strip()]
    )
    headers = (
        ["*"]
        if settings.cors_allow_headers.strip() == "*"
        else [h.strip() for h in settings.cors_allow_headers.split(",") if h.strip()]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=bool(settings.cors_allow_credentials),
        allow_methods=methods,
        allow_headers=headers,
    )

    # Include routers
    app.include_router(health_router, prefix=API_V1_PREFIX)
    app.include_router(auth_router, prefix=API_V1_PREFIX)
    # NOTE: include realtime before pipeline to avoid `/alerts/{id}` shadowing `/alerts/stream`
    app.include_router(realtime_router, prefix=API_V1_PREFIX)
    app.include_router(pipeline_router, prefix=API_V1_PREFIX)
    
    logger.info("FastAPI application created successfully")
    logger.info("API documentation available at /docs")

    return app


# Create the app instance
app = create_app()

