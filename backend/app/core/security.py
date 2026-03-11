"""
Password hashing and JWT token handling.

- Passwords are hashed with bcrypt; never log or return plain passwords.
- JWT subject (sub) is the user's ID (str) for get_current_user lookup.
"""
from datetime import datetime, timezone, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings


def hash_password(plain: str) -> str:
    """Hash a plain-text password. Do not log or store the plain value."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if the plain password matches the hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(subject: str | Any, expires_delta: timedelta | None = None) -> str:
    """
    Create a JWT access token.
    subject: typically the user id (str) for lookup in get_current_user.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt_access_token_expire_minutes)
    expire = now + expires_delta
    to_encode = {"sub": str(subject), "exp": expire, "iat": now}
    return jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict | None:
    """
    Decode and validate JWT. Returns payload dict or None if invalid/expired.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError:
        return None
