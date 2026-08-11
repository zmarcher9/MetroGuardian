"""
Shared pytest fixtures for the backend test suite.

DB-dependent tests use the real DATABASE_URL from backend/.env (there is no
separate local test database). Each test gets an isolated transaction that is
rolled back afterwards (via a SAVEPOINT), so nothing written during a test is
ever actually persisted. If the configured database can't be reached at all,
`db`-marked tests are skipped rather than failed, so CI (which only has a
placeholder DATABASE_URL) stays green.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models import Base


@pytest.fixture(scope="session")
def db_available() -> bool:
    """Best-effort check for whether DATABASE_URL is actually reachable."""

    async def _check() -> bool:
        settings = get_settings()
        engine = create_async_engine(settings.database_url, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=5)
            return True
        except Exception:
            return False
        finally:
            await engine.dispose()

    return asyncio.run(_check())


@pytest.fixture(scope="session")
def db_engine(db_available: bool) -> AsyncEngine:
    if not db_available:
        pytest.skip("DATABASE_URL is not reachable - skipping DB-dependent tests")

    settings = get_settings()
    # NullPool: every checkout opens a fresh connection bound to whichever event
    # loop is currently running, so pooled connections never leak across the
    # separate event loops pytest-asyncio spins up per test.
    engine = create_async_engine(settings.database_url, future=True, poolclass=NullPool)

    async def _create_schema() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create_schema())
    return engine


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """
    An AsyncSession bound to a single connection + outer transaction that is
    rolled back at the end of the test, even if application code calls
    `session.commit()` (that just closes the inner SAVEPOINT, not the outer
    transaction).
    """
    async with db_engine.connect() as conn:
        await conn.begin()
        session_factory = async_sessionmaker(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        async with session_factory() as session:
            yield session
        await conn.rollback()


@pytest_asyncio.fixture
async def plain_client() -> AsyncIterator[AsyncClient]:
    """An HTTP client for routes that don't touch the database (e.g. /health)."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """An HTTP client whose `get_db` dependency is overridden to use the
    per-test, rolled-back `db_session`."""
    from app.db.session import get_db
    from app.main import app

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)
