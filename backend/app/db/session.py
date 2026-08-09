from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import get_settings
from app.models import Base  # noqa: F401 - ensure all models are registered

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,           # set True if you want raw SQL logs
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


async def get_db():
    """
    FastAPI dependency that provides an async database session.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

