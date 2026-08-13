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
from app.core.rate_limit import reset_rate_limits
from app.models import Base
from app.services.routing_service import _clear_osrm_cache


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> None:
    """
    The auth rate limiter (app/core/rate_limit.py) is deliberately strict
    (e.g. 5 signups/hour per IP) and its state is process-global, not
    per-test - without this, tests would trip each other's limits since the
    test transport always reports the same fake client IP.
    """
    reset_rate_limits()


@pytest.fixture(autouse=True)
def _reset_osrm_cache() -> None:
    """
    The OSRM route cache (app/services/routing_service.py) is process-global,
    not per-test. Several existing tests reuse the same origin/destination
    constants (see test_routing_service.py's ORIGIN/DESTINATION) expecting
    each call to actually hit the mocked transport - without this reset,
    whichever test populates the cache first would silently serve a stale
    result to every test that runs after it.
    """
    _clear_osrm_cache()


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
    # https:// (not http://) even though ASGITransport makes no real network
    # call and the scheme is otherwise symbolic - httpx's cookie jar enforces
    # the Secure cookie attribute the same way a real browser does, and
    # auth cookies are Secure by default, so a plain http:// base_url would
    # silently refuse to resend them on the next request in a test.
    async with AsyncClient(transport=transport, base_url="https://testserver") as ac:
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
        # https:// - see the comment in plain_client() above.
        async with AsyncClient(transport=transport, base_url="https://testserver") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)


def csrf_headers(client: AsyncClient) -> dict[str, str]:
    """
    The X-CSRF-Token header a mutating request needs, echoing whatever value
    CSRFMiddleware has already minted into the client's cookie jar (from any
    prior request - GET or a previously-rejected mutating one both mint it).
    """
    settings = get_settings()
    return {settings.csrf_header_name: client.cookies.get(settings.csrf_cookie_name) or ""}
