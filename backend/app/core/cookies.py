"""
Helpers for setting/clearing the auth + CSRF cookies. Centralized here so
routes_auth.py and CSRFMiddleware apply identical cookie attributes - a
mismatched Path/Domain between set and delete calls means the browser treats
them as different cookies and silently fails to clear the old one.
"""
from __future__ import annotations

import secrets

from fastapi import Request, Response

from app.core.config import get_settings

REFRESH_TOKEN_COOKIE_PATH = "/api/v1/auth"


def set_auth_cookies(response: Response, *, access_token: str, refresh_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.access_token_cookie_name,
        value=access_token,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )
    response.set_cookie(
        key=settings.refresh_token_cookie_name,
        value=refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path=REFRESH_TOKEN_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )


def clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(key=settings.access_token_cookie_name, path="/")
    response.delete_cookie(key=settings.refresh_token_cookie_name, path=REFRESH_TOKEN_COOKIE_PATH)


def ensure_csrf_cookie(request: Request, response: Response) -> None:
    """Mint the CSRF double-submit cookie if the request doesn't already have one."""
    settings = get_settings()
    if request.cookies.get(settings.csrf_cookie_name):
        return
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=secrets.token_urlsafe(32),
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path="/",
        httponly=False,  # must be JS-readable so the frontend can echo it as a header
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )
