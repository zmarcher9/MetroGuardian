from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.refresh_token import RefreshToken
from tests.conftest import csrf_headers

pytestmark = pytest.mark.db

settings = get_settings()


async def _prime_csrf(client: AsyncClient) -> None:
    """A safe GET mints the CSRF cookie so a subsequent mutating call has one to echo."""
    await client.get("/api/v1/auth/me")


# ---------------------------------------------------------------------------
# signup / login (web/cookie flow)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signup_sets_cookies_and_returns_user(client: AsyncClient):
    await _prime_csrf(client)
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": "signup-ok@example.com", "password": "password1"},
        headers=csrf_headers(client),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "signup-ok@example.com"
    assert "access_token" not in body
    assert "refresh_token" not in body
    assert client.cookies.get(settings.access_token_cookie_name)
    assert client.cookies.get(settings.refresh_token_cookie_name)


@pytest.mark.asyncio
async def test_signup_rejects_password_without_digit(client: AsyncClient):
    await _prime_csrf(client)
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": "weak-pw@example.com", "password": "noDigitsHere"},
        headers=csrf_headers(client),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_signup_rejects_short_password(client: AsyncClient):
    await _prime_csrf(client)
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": "short-pw@example.com", "password": "a1"},
        headers=csrf_headers(client),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_signup_duplicate_email_conflicts(client: AsyncClient):
    await _prime_csrf(client)
    payload = {"email": "duplicate@example.com", "password": "password1"}
    first = await client.post("/api/v1/auth/signup", json=payload, headers=csrf_headers(client))
    assert first.status_code == 200

    second = await client.post("/api/v1/auth/signup", json=payload, headers=csrf_headers(client))
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_signup_without_csrf_header_is_rejected(client: AsyncClient):
    await _prime_csrf(client)
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": "no-csrf@example.com", "password": "password1"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_login_with_correct_credentials_sets_cookies(client: AsyncClient):
    await _prime_csrf(client)
    payload = {"email": "login-ok@example.com", "password": "password1"}
    await client.post("/api/v1/auth/signup", json=payload, headers=csrf_headers(client))

    resp = await client.post("/api/v1/auth/login", json=payload, headers=csrf_headers(client))
    assert resp.status_code == 200
    assert resp.json()["email"] == payload["email"]
    assert client.cookies.get(settings.access_token_cookie_name)


@pytest.mark.asyncio
async def test_login_with_wrong_password_is_unauthorized(client: AsyncClient):
    await _prime_csrf(client)
    await client.post(
        "/api/v1/auth/signup",
        json={"email": "login-wrong@example.com", "password": "password1"},
        headers=csrf_headers(client),
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "login-wrong@example.com", "password": "wrong-password-1"},
        headers=csrf_headers(client),
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_with_unknown_email_is_unauthorized(client: AsyncClient):
    await _prime_csrf(client)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "does-not-exist@example.com", "password": "password1"},
        headers=csrf_headers(client),
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /auth/me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_current_user_via_cookie(client: AsyncClient):
    await _prime_csrf(client)
    payload = {"email": "me-ok@example.com", "password": "password1"}
    await client.post("/api/v1/auth/signup", json=payload, headers=csrf_headers(client))

    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == payload["email"]


@pytest.mark.asyncio
async def test_me_rejects_invalid_bearer_token(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /auth/refresh - rotation, reuse detection, expiry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_rotates_both_cookies(client: AsyncClient):
    await _prime_csrf(client)
    payload = {"email": "refresh-ok@example.com", "password": "password1"}
    await client.post("/api/v1/auth/signup", json=payload, headers=csrf_headers(client))

    old_at = client.cookies.get(settings.access_token_cookie_name)
    old_rt = client.cookies.get(settings.refresh_token_cookie_name)

    resp = await client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
    assert resp.status_code == 200

    new_at = client.cookies.get(settings.access_token_cookie_name)
    new_rt = client.cookies.get(settings.refresh_token_cookie_name)
    assert new_at and new_at != old_at
    assert new_rt and new_rt != old_rt


@pytest.mark.asyncio
async def test_refresh_reuse_of_rotated_token_revokes_family(client: AsyncClient):
    await _prime_csrf(client)
    payload = {"email": "reuse-ok@example.com", "password": "password1"}
    await client.post("/api/v1/auth/signup", json=payload, headers=csrf_headers(client))

    old_rt = client.cookies.get(settings.refresh_token_cookie_name)
    assert old_rt is not None

    # Legitimate rotation.
    resp = await client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
    assert resp.status_code == 200
    rotated_rt = client.cookies.get(settings.refresh_token_cookie_name)
    assert rotated_rt is not None

    # Replay the pre-rotation token - simulates a stolen/leaked token being used
    # after the legitimate client already rotated past it.
    client.cookies.set(settings.refresh_token_cookie_name, old_rt)
    reuse_resp = await client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
    assert reuse_resp.status_code == 401

    # The whole family should now be dead - even the token that was
    # legitimately rotated to must also be rejected.
    client.cookies.set(settings.refresh_token_cookie_name, rotated_rt)
    also_dead_resp = await client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
    assert also_dead_resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_with_expired_token_is_rejected(client: AsyncClient, db_session: AsyncSession):
    await _prime_csrf(client)
    payload = {"email": "expired-rt@example.com", "password": "password1"}
    await client.post("/api/v1/auth/signup", json=payload, headers=csrf_headers(client))

    result = await db_session.execute(select(RefreshToken).order_by(RefreshToken.created_at.desc()).limit(1))
    row = result.scalar_one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()

    resp = await client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_without_cookie_is_rejected(client: AsyncClient):
    await _prime_csrf(client)
    resp = await client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /auth/logout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_clears_cookies_and_revokes_token(client: AsyncClient):
    await _prime_csrf(client)
    payload = {"email": "logout-ok@example.com", "password": "password1"}
    await client.post("/api/v1/auth/signup", json=payload, headers=csrf_headers(client))

    logout_resp = await client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    assert logout_resp.status_code == 204
    assert not client.cookies.get(settings.access_token_cookie_name)

    me_resp = await client.get("/api/v1/auth/me")
    assert me_resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_is_idempotent_with_no_session(client: AsyncClient):
    await _prime_csrf(client)
    resp = await client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# mobile (Bearer + body-token) flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mobile_signup_returns_tokens_in_body_and_sets_no_cookies(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": "mobile-signup@example.com", "password": "password1"},
        headers={"X-Client-Type": "mobile"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["email"] == "mobile-signup@example.com"
    assert not client.cookies.get(settings.access_token_cookie_name)


@pytest.mark.asyncio
async def test_mobile_bearer_token_authenticates_me(client: AsyncClient):
    signup_resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": "mobile-me@example.com", "password": "password1"},
        headers={"X-Client-Type": "mobile"},
    )
    access_token = signup_resp.json()["access_token"]

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "mobile-me@example.com"


@pytest.mark.asyncio
async def test_mobile_refresh_uses_body_token_and_bypasses_csrf(client: AsyncClient):
    signup_resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": "mobile-refresh@example.com", "password": "password1"},
        headers={"X-Client-Type": "mobile"},
    )
    old_refresh_token = signup_resp.json()["refresh_token"]

    # No CSRF header attached - must still succeed, since this request has no
    # cookie-based session for CSRF to protect.
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh_token},
        headers={"X-Client-Type": "mobile"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["refresh_token"] != old_refresh_token


# ---------------------------------------------------------------------------
# full lifecycle smoke test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_auth_lifecycle(client: AsyncClient):
    await _prime_csrf(client)
    payload = {"email": "lifecycle@example.com", "password": "password1"}

    signup_resp = await client.post("/api/v1/auth/signup", json=payload, headers=csrf_headers(client))
    assert signup_resp.status_code == 200

    me_resp = await client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200

    old_rt = client.cookies.get(settings.refresh_token_cookie_name)
    assert old_rt is not None
    refresh_resp = await client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
    assert refresh_resp.status_code == 200

    client.cookies.set(settings.refresh_token_cookie_name, old_rt)
    reuse_resp = await client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
    assert reuse_resp.status_code == 401

    # Family is dead; even a correctly-remembered current token now fails.
    logout_resp = await client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    assert logout_resp.status_code == 204

    final_me_resp = await client.get("/api/v1/auth/me")
    assert final_me_resp.status_code == 401
