"""
Stricter, auth-specific rate limiting on top of the general per-IP limit in
SimpleRateLimitMiddleware (app/core/middleware.py). 120 req/min (the global
default) is fine for general API use but far too permissive to meaningfully
slow down credential-stuffing/brute-force login attempts or mass fake-account
signup.

In-memory, single-instance only - same documented limitation as the global
limiter. Swap for a shared store (e.g. Redis) before running more than one
backend instance.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.core.config import get_settings


@dataclass
class _Bucket:
    window_start: float
    count: int


_login_buckets: dict[str, _Bucket] = {}
_signup_buckets: dict[str, _Bucket] = {}


def get_client_ip(request: Request) -> str:
    return (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or request.headers.get("x-real-ip", "").strip()
        or (request.client.host if request.client else "unknown")
    )


def _hit(buckets: dict[str, _Bucket], key: str, limit: int, window_seconds: int) -> None:
    now = time.time()
    bucket = buckets.get(key)
    if bucket is None or (now - bucket.window_start) >= window_seconds:
        bucket = _Bucket(window_start=now, count=0)
        buckets[key] = bucket
    bucket.count += 1
    if bucket.count > limit:
        retry_after = int(bucket.window_start + window_seconds - now)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again later.",
            headers={"Retry-After": str(max(0, retry_after))},
        )


def check_login_attempt(request: Request, email: str) -> None:
    """Raises 429 if this IP+email combo has exceeded the login attempt limit."""
    settings = get_settings()
    key = f"{get_client_ip(request)}:{email.strip().lower()}"
    _hit(_login_buckets, key, settings.rate_limit_login_attempts, settings.rate_limit_login_window_seconds)


def check_signup_attempt(request: Request) -> None:
    """Raises 429 if this IP has exceeded the signup attempt limit."""
    settings = get_settings()
    _hit(_signup_buckets, get_client_ip(request), settings.rate_limit_signup_attempts, settings.rate_limit_signup_window_seconds)


def reset_rate_limits() -> None:
    """Test-only: clear all accumulated state between tests."""
    _login_buckets.clear()
    _signup_buckets.clear()
