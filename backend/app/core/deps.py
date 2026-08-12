"""
Shared FastAPI dependencies (e.g. get_current_user).
"""
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

# auto_error=False: a missing Authorization header must not 401 by itself -
# the access token may instead be in the mg_at cookie (the web client's
# transport). Absence of both is what actually 401s, below.
_bearer_scheme = HTTPBearer(auto_error=False)


def _extract_access_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    """
    Read the access token from either transport:
    - Web clients: the httpOnly `mg_at` cookie.
    - Mobile/native clients (no cookie jar): an `Authorization: Bearer` header.
    Cookie takes precedence when both are present.
    """
    settings = get_settings()
    cookie_token = request.cookies.get(settings.access_token_cookie_name)
    if cookie_token:
        return cookie_token
    if credentials is not None:
        return credentials.credentials
    return None


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Validate the access token (cookie or Bearer header) and return the current user.
    Raises 401 if the token is missing, invalid, expired, or the user no longer exists.
    """
    token = _extract_access_token(request, credentials)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = UUID(sub)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Same as get_current_user, but additionally requires is_admin. There is no
    HTTP path that lets a user grant themselves admin - see
    backend/scripts/promote_admin.py.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return current_user
