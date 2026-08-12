"""
Tests for the auth-specific rate limiter (app/core/rate_limit.py) and the
refresh-token cleanup job (app/services/token_cleanup.py).

Admin-role gating of the ingest endpoints is covered in test_pipeline_api.py
alongside the rest of that router's tests.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.token_cleanup import cleanup_expired_refresh_tokens
from tests.conftest import csrf_headers

pytestmark = pytest.mark.db

settings = get_settings()


@pytest.mark.asyncio
async def test_login_rate_limit_triggers_429(client: AsyncClient):
    await client.get("/api/v1/health")  # mints the CSRF cookie
    payload = {"email": "rate-limit-login@example.com", "password": "password1"}
    await client.post("/api/v1/auth/signup", json=payload, headers=csrf_headers(client))

    # Wrong password on every attempt - the limiter still counts them
    # regardless of outcome (it triggers before credentials are checked).
    bad_payload = {"email": payload["email"], "password": "wrong-password-1"}
    for _ in range(settings.rate_limit_login_attempts):
        resp = await client.post("/api/v1/auth/login", json=bad_payload, headers=csrf_headers(client))
        assert resp.status_code == 401

    over_limit_resp = await client.post("/api/v1/auth/login", json=bad_payload, headers=csrf_headers(client))
    assert over_limit_resp.status_code == 429
    assert "Retry-After" in over_limit_resp.headers


@pytest.mark.asyncio
async def test_signup_rate_limit_triggers_429(client: AsyncClient):
    await client.get("/api/v1/health")  # mints the CSRF cookie
    for i in range(settings.rate_limit_signup_attempts):
        resp = await client.post(
            "/api/v1/auth/signup",
            json={"email": f"rate-limit-signup-{i}@example.com", "password": "password1"},
            headers=csrf_headers(client),
        )
        assert resp.status_code == 200

    over_limit_resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": "rate-limit-signup-over@example.com", "password": "password1"},
        headers=csrf_headers(client),
    )
    assert over_limit_resp.status_code == 429
    assert "Retry-After" in over_limit_resp.headers


@pytest.mark.asyncio
async def test_login_rate_limit_is_scoped_per_email(client: AsyncClient):
    """A different email from the same IP must not be blocked by another
    email's exhausted limit - the limiter is keyed on IP+email, not IP alone."""
    await client.get("/api/v1/health")  # mints the CSRF cookie
    bad_payload = {"email": "victim-a@example.com", "password": "wrong-password-1"}
    for _ in range(settings.rate_limit_login_attempts + 1):
        await client.post("/api/v1/auth/login", json=bad_payload, headers=csrf_headers(client))

    other_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "victim-b@example.com", "password": "wrong-password-1"},
        headers=csrf_headers(client),
    )
    assert other_resp.status_code == 401  # not 429 - a different account, not rate-limited


@pytest.mark.asyncio
async def test_cleanup_deletes_old_rows_but_keeps_recent_ones(client: AsyncClient, db_session: AsyncSession):
    await client.get("/api/v1/health")  # mints the CSRF cookie
    payload = {"email": "cleanup-target@example.com", "password": "password1"}
    await client.post("/api/v1/auth/signup", json=payload, headers=csrf_headers(client))
    user_id = (await db_session.execute(select(User.id).where(User.email == payload["email"]))).scalar_one()

    now = datetime.now(timezone.utc)
    grace = timedelta(days=settings.refresh_token_cleanup_grace_days)

    old_expired = RefreshToken(
        user_id=user_id,
        family_id=uuid4(),
        token_hash="old-expired-hash",
        expires_at=now - grace - timedelta(days=1),
    )
    recent_expired = RefreshToken(
        user_id=user_id,
        family_id=uuid4(),
        token_hash="recent-expired-hash",
        expires_at=now - timedelta(days=1),  # expired, but within the grace window
    )
    old_revoked = RefreshToken(
        user_id=user_id,
        family_id=uuid4(),
        token_hash="old-revoked-hash",
        expires_at=now + timedelta(days=30),  # not expired
        revoked_at=now - grace - timedelta(days=1),  # but revoked long enough ago
    )
    db_session.add_all([old_expired, recent_expired, old_revoked])
    await db_session.commit()

    deleted = await cleanup_expired_refresh_tokens(db_session)
    assert deleted >= 2  # old_expired and old_revoked, at minimum (plus whatever signup created, still fresh)

    remaining_hashes = {
        row.token_hash for row in (await db_session.execute(select(RefreshToken.token_hash))).all()
    }
    assert "old-expired-hash" not in remaining_hashes
    assert "old-revoked-hash" not in remaining_hashes
    assert "recent-expired-hash" in remaining_hashes
