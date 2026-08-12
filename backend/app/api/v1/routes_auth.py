"""
Auth routes: signup, login, me, refresh, logout.

Web clients (default): tokens are delivered via httpOnly cookies
(mg_at/mg_rt) and never appear in the response body.

Mobile/native clients (send `X-Client-Type: mobile`): there's no cookie jar,
so tokens are returned in the response body instead, and the refresh token
must be sent back explicitly on /auth/refresh and /auth/logout rather than
relying on a cookie.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.cookies import clear_auth_cookies, set_auth_cookies
from app.core.deps import get_current_user
from app.core.rate_limit import check_login_attempt, check_signup_attempt
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.db.session import get_db
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, SignUpRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def _is_mobile_client(request: Request) -> bool:
    return request.headers.get("x-client-type", "").strip().lower() == "mobile"


async def _issue_refresh_token(db: AsyncSession, user_id: UUID, family_id: UUID) -> tuple[str, RefreshToken]:
    """Create+store a new refresh token row in the given family. Returns (raw_token, row)."""
    settings = get_settings()
    raw_token = generate_refresh_token()
    row = RefreshToken(
        user_id=user_id,
        family_id=family_id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(row)
    await db.flush()  # populate row.id
    return raw_token, row


async def _start_session(request: Request, response: Response, db: AsyncSession, user: User) -> TokenResponse | None:
    """
    Issue an access token + a brand-new refresh token family for `user`.
    Web clients: sets cookies, returns None (nothing in the body).
    Mobile clients: returns a TokenResponse to put in the body, sets no cookies.
    """
    access_token = create_access_token(str(user.id))
    refresh_token, _row = await _issue_refresh_token(db, user.id, family_id=uuid4())

    if _is_mobile_client(request):
        return TokenResponse(access_token=access_token, refresh_token=refresh_token, user=UserResponse.model_validate(user))
    set_auth_cookies(response, access_token=access_token, refresh_token=refresh_token)
    return None


@router.post("/signup", response_model=UserResponse | TokenResponse)
async def signup(
    request: Request,
    response: Response,
    body: SignUpRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse | TokenResponse:
    """
    Register a new user and start a session (new refresh-token family).
    """
    check_signup_attempt(request)
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )
    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.flush()

    token_response = await _start_session(request, response, db, user)
    await db.commit()
    await db.refresh(user)
    logger.info("User signed up", extra={"email": user.email})
    return token_response or UserResponse.model_validate(user)


@router.post("/login", response_model=UserResponse | TokenResponse)
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse | TokenResponse:
    """
    Authenticate and start a new session (new refresh-token family).
    """
    check_login_attempt(request, body.email)
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if user is None or user.password_hash is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token_response = await _start_session(request, response, db, user)
    await db.commit()
    return token_response or UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
async def me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """
    Return the current authenticated user.
    """
    return UserResponse.model_validate(current_user)


@router.post("/refresh", response_model=UserResponse | TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    body: RefreshRequest | None = None,
) -> UserResponse | TokenResponse:
    """
    Rotate the refresh token: the presented token is revoked and replaced by a
    new one in the same family, and a new access token is issued.

    Presenting an already-revoked token is treated as token theft/replay and
    revokes the entire family, forcing a full re-login.
    """
    settings = get_settings()
    raw_token = (body.refresh_token if body else None) if _is_mobile_client(request) else None
    raw_token = raw_token or request.cookies.get(settings.refresh_token_cookie_name)

    if not raw_token:
        clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token provided")

    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token)))
    row = result.scalar_one_or_none()

    if row is None:
        clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    now = datetime.now(timezone.utc)

    if row.revoked_at is not None:
        # Reuse of an already-rotated (or already-logged-out) token: treat as
        # theft/replay and kill the entire lineage, not just this token.
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await db.commit()
        clear_auth_cookies(response)
        logger.warning("Refresh token reuse detected; family revoked", extra={"family_id": str(row.family_id)})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has already been used")

    if row.expires_at < now:
        clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    user_result = await db.execute(select(User).where(User.id == row.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access_token = create_access_token(str(user.id))
    new_raw_token, new_row = await _issue_refresh_token(db, user.id, family_id=row.family_id)
    row.revoked_at = now
    row.replaced_by_id = new_row.id

    if _is_mobile_client(request):
        await db.commit()
        return TokenResponse(access_token=access_token, refresh_token=new_raw_token, user=UserResponse.model_validate(user))

    set_auth_cookies(response, access_token=access_token, refresh_token=new_raw_token)
    await db.commit()
    return UserResponse.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    body: RefreshRequest | None = None,
) -> None:
    """
    Revoke the current refresh token (if any) and clear auth cookies.
    Always succeeds, even with no active session - logout is idempotent.
    """
    settings = get_settings()
    raw_token = (body.refresh_token if body else None) or request.cookies.get(settings.refresh_token_cookie_name)
    if raw_token:
        result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token)))
        row = result.scalar_one_or_none()
        if row is not None and row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            await db.commit()
    clear_auth_cookies(response)
