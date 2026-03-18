from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        # If you add HTML later, consider CSP. For APIs, we keep it minimal/non-breaking.
        return response


@dataclass
class _RateBucket:
    window_start: float
    count: int


class SimpleRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Very small in-memory IP rate limiter.

    - Good enough for dev / single instance.
    - For production multi-instance, replace with Redis-backed limiter.
    """

    def __init__(self, app):
        super().__init__(app)
        self._buckets: dict[str, _RateBucket] = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        settings = get_settings()
        limit = max(1, int(settings.rate_limit_requests))
        window = max(1, int(settings.rate_limit_window_seconds))

        # Try common headers first (Render/Fly/etc), fall back to client host.
        ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or request.headers.get("x-real-ip", "").strip()
            or (request.client.host if request.client else "unknown")
        )

        now = time.time()
        bucket = self._buckets.get(ip)
        if bucket is None or (now - bucket.window_start) >= window:
            bucket = _RateBucket(window_start=now, count=0)
            self._buckets[ip] = bucket

        bucket.count += 1
        if bucket.count > limit:
            retry_after = int(bucket.window_start + window - now)
            return Response(
                content="Rate limit exceeded",
                status_code=429,
                headers={"Retry-After": str(max(0, retry_after))},
                media_type="text/plain",
            )

        return await call_next(request)

