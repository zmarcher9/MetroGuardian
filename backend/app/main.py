import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text
from app.api.v1.routes_health import router as health_router
from app.core.logging_config import setup_logging
from app.core.config import get_settings
from app.db.session import engine

# Initialize logging FIRST, before any other imports that might log
setup_logging()

# Get logger after logging is configured
logger = logging.getLogger(__name__)


async def test_database_connectivity():
    """
    Test database connectivity on startup.
    
    This is an optional check to ensure the database is accessible
    before the application starts serving requests.
    """
    try:
        settings = get_settings()
        logger.info("Testing database connectivity...")
        
        # Test connection by executing a simple query
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        
        logger.info("Database connectivity test passed")
        logger.info(f"Database URL: {settings.get_database_url_masked()}")
    except Exception as e:
        logger.warning(
            f"Database connectivity test failed: {e} | "
            f"Application will continue to start, but database operations may fail"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI app startup and shutdown events.
    
    - On startup: Test database connectivity (optional)
    - On shutdown: Clean up resources
    """
    # Startup
    logger.info("Application startup: Testing database connectivity...")
    await test_database_connectivity()
    
    yield
    
    # Shutdown
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

    # Include routers
    app.include_router(health_router, prefix="/api/v1")
    
    logger.info("FastAPI application created successfully")
    logger.info(f"API documentation available at /docs")

    return app


# Create the app instance
app = create_app()

