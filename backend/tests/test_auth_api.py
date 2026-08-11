import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.db


@pytest.mark.asyncio
async def test_signup_returns_access_token(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": "signup-ok@example.com", "password": "password1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


@pytest.mark.asyncio
async def test_signup_rejects_password_without_digit(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": "weak-pw@example.com", "password": "noDigitsHere"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_signup_rejects_short_password(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": "short-pw@example.com", "password": "a1"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_signup_duplicate_email_conflicts(client: AsyncClient):
    payload = {"email": "duplicate@example.com", "password": "password1"}
    first = await client.post("/api/v1/auth/signup", json=payload)
    assert first.status_code == 200

    second = await client.post("/api/v1/auth/signup", json=payload)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_login_with_correct_credentials_succeeds(client: AsyncClient):
    payload = {"email": "login-ok@example.com", "password": "password1"}
    await client.post("/api/v1/auth/signup", json=payload)

    resp = await client.post("/api/v1/auth/login", json=payload)
    assert resp.status_code == 200
    assert resp.json()["access_token"]


@pytest.mark.asyncio
async def test_login_with_wrong_password_is_unauthorized(client: AsyncClient):
    await client.post(
        "/api/v1/auth/signup",
        json={"email": "login-wrong@example.com", "password": "password1"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "login-wrong@example.com", "password": "wrong-password-1"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_with_unknown_email_is_unauthorized(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "does-not-exist@example.com", "password": "password1"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_bearer_token(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_me_returns_current_user_for_valid_token(client: AsyncClient):
    payload = {"email": "me-ok@example.com", "password": "password1"}
    signup = await client.post("/api/v1/auth/signup", json=payload)
    token = signup.json()["access_token"]

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == payload["email"]


@pytest.mark.asyncio
async def test_me_rejects_invalid_token(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
