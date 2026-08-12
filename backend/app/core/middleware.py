from __future__ import annotations

import hmac
import time
from dataclasses import dataclass
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.cookies import ensure_csrf_cookie
from app.core.rate_limit import get_client_ip


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        # If you add HTML later, consider CSP. For APIs, we keep it minimal/non-breaking.
        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Double-submit cookie CSRF protection for the cookie-authenticated (web)
    flow. Mints the `mg_csrf` cookie for any client that doesn't have one yet
    (JS-readable, unlike the auth cookies), and requires mutating requests to
    echo it back in a header.

    Mobile/native clients (no cookie jar - identified by an `Authorization`
    header, or by `X-Client-Type: mobile` on the token-issuing calls that
    don't have a token to attach yet) are exempt: CSRF is an attack that
    relies on a browser automatically attaching cookies to a forged
    cross-site request, which doesn't apply to a client that isn't using a
    cookie jar in the first place.
    """

    _SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        settings = get_settings()
        is_mobile = "authorization" in request.headers or request.headers.get("x-client-type", "").strip().lower() == "mobile"

        if request.method not in self._SAFE_METHODS and not is_mobile:
            cookie_value = request.cookies.get(settings.csrf_cookie_name)
            header_value = request.headers.get(settings.csrf_header_name)
            if not cookie_value or not header_value or not hmac.compare_digest(cookie_value, header_value):
                response = Response(content="CSRF token missing or invalid", status_code=403, media_type="text/plain")
                # Mint the cookie even on rejection, so a client whose very
                # first request is a mutating one (no prior GET to mint it
                # off of) can retry instead of being stuck in a 403 loop.
                ensure_csrf_cookie(request, response)
                return response

        response = await call_next(request)
        ensure_csrf_cookie(request, response)
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

        ip = get_client_ip(request)

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

