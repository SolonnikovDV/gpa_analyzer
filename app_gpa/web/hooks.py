"""Flask application-level hooks: before_request, after_request, errorhandler.

These are registered on the Flask app (not on a blueprint) so they apply to
ALL requests regardless of which blueprint handles them.
"""
from __future__ import annotations

import hmac
import time
from typing import Optional

from flask import Flask, Response, g, request, session
from werkzeug.exceptions import RequestEntityTooLarge

from core.settings import settings
from modules.analysis.api_contracts import api_error
from modules.analysis.observability import generate_request_id, log_event
from web.context import _rate_limiter


def _request_client_identity() -> str:
    forwarded_for = (request.headers.get("X-Forwarded-For") or "").strip()
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or "unknown"
    return request.remote_addr or "unknown"


def _is_request_authorized() -> bool:
    if not settings.basic_auth_enabled:
        return True
    auth = request.authorization
    if not auth:
        return False
    username = auth.username or ""
    password = auth.password or ""
    return hmac.compare_digest(username, settings.basic_auth_username) and hmac.compare_digest(
        password, settings.basic_auth_password
    )


def _unauthorized_response() -> Response:
    response = Response("Authentication required", 401)
    response.headers["WWW-Authenticate"] = 'Basic realm="GPA Analyzer"'
    return response


def _is_public_endpoint() -> bool:
    return request.endpoint in ("static",) or request.path.startswith("/health")


def register_hooks(app: Flask) -> None:
    """Attach all lifecycle hooks to the Flask application."""

    @app.before_request
    def apply_session_baseline():
        g.request_id = (request.headers.get("X-Request-ID") or "").strip() or generate_request_id()
        g.request_started_at = time.time()
        session.permanent = True
        if _is_public_endpoint():
            return None
        log_event(
            "http.request.started",
            request_id=g.request_id,
            method=request.method,
            path=request.path,
            remote_addr=_request_client_identity(),
        )
        if not _is_request_authorized():
            log_event(
                "http.request.unauthorized",
                request_id=g.request_id,
                method=request.method,
                path=request.path,
            )
            return _unauthorized_response()
        if _rate_limiter is not None:
            decision = _rate_limiter.check(_request_client_identity())
            if not decision.allowed:
                log_event(
                    "http.request.rate_limited",
                    request_id=g.request_id,
                    method=request.method,
                    path=request.path,
                    retry_after_seconds=decision.retry_after_seconds,
                )
                resp = api_error(
                    "rate_limit_exceeded",
                    "Слишком много запросов. Повторите позже.",
                    http_status=429,
                    retry_after_seconds=decision.retry_after_seconds,
                )
                resp.headers["Retry-After"] = str(decision.retry_after_seconds)
                return resp
        return None

    @app.after_request
    def apply_security_headers(response: Response) -> Response:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        request_id = getattr(g, "request_id", "")
        if request_id:
            response.headers.setdefault("X-Request-ID", request_id)
        if request.path.startswith("/api/") or request.path.startswith("/stream/"):
            response.headers.setdefault("Cache-Control", "no-store")
        started_at = getattr(g, "request_started_at", None)
        duration_ms = None
        if started_at is not None:
            duration_ms = int((time.time() - started_at) * 1000)
        log_event(
            "http.request.completed",
            request_id=request_id,
            method=request.method,
            path=request.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def handle_request_entity_too_large(_error):
        return api_error(
            "request_too_large",
            "Размер запроса превышает допустимый лимит.",
            http_status=413,
            max_content_length_bytes=settings.max_content_length_bytes,
        )
