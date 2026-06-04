"""FastAPI middleware stack — mirrors web/hooks.py for the FastAPI layer.

Registered in api/app_factory.py so that all /api/* routes (served directly
by FastAPI, not via WSGIMiddleware) get auth, rate-limiting, and security
headers on par with the Flask layer.
"""
from __future__ import annotations

import hmac
import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from core.settings import settings
from modules.analysis.observability import generate_request_id, log_event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",", 1)[0].strip() or "unknown"
    return request.client.host if request.client else "unknown"


def _is_public(path: str) -> bool:
    return path.startswith("/health") or path.startswith("/docs") or path.startswith("/openapi")


def _is_authorized(request: Request) -> bool:
    if not settings.basic_auth_enabled:
        return True
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("basic "):
        return False
    try:
        import base64
        decoded = base64.b64decode(auth[6:]).decode("utf-8")
        username, _, password = decoded.partition(":")
        return hmac.compare_digest(username, settings.basic_auth_username) and hmac.compare_digest(
            password, settings.basic_auth_password
        )
    except Exception:
        return False


def _unauthorized_json() -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": "Authentication required"},
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="GPA Analyzer"'},
    )


def _rate_limit_json(retry_after: int) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": "Слишком много запросов. Повторите позже.", "retry_after_seconds": retry_after},
        status_code=429,
        headers={"Retry-After": str(retry_after)},
    )


# ---------------------------------------------------------------------------
# Middleware classes
# ---------------------------------------------------------------------------


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign X-Request-ID to every request; propagate to response."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        rid = request.headers.get("x-request-id", "").strip() or generate_request_id()
        request.state.request_id = rid
        request.state.started_at = time.time()
        response = await call_next(request)
        response.headers.setdefault("X-Request-ID", rid)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security response headers and log completed requests."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        path = request.url.path
        if path.startswith("/api/") or path.startswith("/stream/"):
            response.headers.setdefault("Cache-Control", "no-store")
        rid = getattr(request.state, "request_id", "")
        if rid:
            response.headers.setdefault("X-Request-ID", rid)
        started_at = getattr(request.state, "started_at", None)
        duration_ms = int((time.time() - started_at) * 1000) if started_at else None
        log_event(
            "http.request.completed",
            request_id=rid,
            method=request.method,
            path=path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            framework="fastapi",
        )
        return response


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """HTTP Basic-Auth gate (skipped for public endpoints and when auth is disabled)."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if _is_public(request.url.path):
            return await call_next(request)
        if not _is_authorized(request):
            rid = getattr(request.state, "request_id", "")
            log_event(
                "http.request.unauthorized",
                request_id=rid,
                method=request.method,
                path=request.url.path,
                framework="fastapi",
            )
            return _unauthorized_json()
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-bucket rate limiter (skipped when rate-limiting is disabled)."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        from web.context import _rate_limiter
        self._limiter = _rate_limiter

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if self._limiter is None or _is_public(request.url.path):
            return await call_next(request)
        ip = _client_ip(request)
        decision = self._limiter.check(ip)
        if not decision.allowed:
            rid = getattr(request.state, "request_id", "")
            log_event(
                "http.request.rate_limited",
                request_id=rid,
                method=request.method,
                path=request.url.path,
                retry_after_seconds=decision.retry_after_seconds,
                framework="fastapi",
            )
            return _rate_limit_json(decision.retry_after_seconds)
        return await call_next(request)
