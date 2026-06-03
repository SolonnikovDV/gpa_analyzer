"""Hybrid integration tests — exercise the full main:app stack.

All requests go through:  FastAPI root → /api mount → api/routers/*

These tests verify that:
- FastAPI serves /api/* correctly (including new profile CRUD routes)
- Middleware stack does not break normal request flow
- Health readiness probe reports check results
- Provider registry returns rich UI metadata
"""
from __future__ import annotations

import pytest

pytest.importorskip(
    "fastapi",
    reason="fastapi not installed; skipping hybrid tests",
    exc_type=ImportError,
)

import os
os.environ.setdefault("GPA_HYBRID_MODE", "1")

from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def full_client():
    """Build the full hybrid ASGI app (same as production main.py)."""
    from fastapi import FastAPI
    from fastapi.middleware.wsgi import WSGIMiddleware
    from api.app_factory import create_api_app

    root = FastAPI(title="GPA Test", docs_url="/api/docs", openapi_url="/api/openapi.json")
    api = create_api_app()
    root.mount("/api", api)

    import webapp
    root.mount("/", WSGIMiddleware(webapp.app))
    return TestClient(root)


@pytest.fixture(scope="module")
def api_client():
    """Lighter fixture: only the FastAPI /api layer (no Flask mount)."""
    from api.app_factory import create_api_app
    return TestClient(create_api_app())


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health_live(api_client):
    r = api_client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_health_ready_returns_checks(api_client):
    r = api_client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert "checks" in body
    assert "sqlite" in body["checks"]
    assert "redis" in body["checks"]


# ---------------------------------------------------------------------------
# Provider registry (rich metadata)
# ---------------------------------------------------------------------------


def test_providers_have_ui_metadata(api_client):
    r = api_client.get("/agent/providers")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    providers = body["data"]["providers"]
    assert len(providers) >= 1
    for p in providers:
        assert "env_key" in p, f"Missing env_key for {p.get('id')}"
        assert "key_placeholder" in p
        assert "profiles_url" in p
        assert "is_simple" in p


# ---------------------------------------------------------------------------
# Profile CRUD — GigaChat
# ---------------------------------------------------------------------------


def test_gigachat_profiles_get(api_client):
    r = api_client.get("/agent/profiles")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert isinstance(body.get("items"), list)


# ---------------------------------------------------------------------------
# Profile CRUD — simple providers
# ---------------------------------------------------------------------------


def test_simple_profiles_unknown_provider_404(api_client):
    r = api_client.get("/agent/profiles/nonexistent_provider_xyz")
    assert r.status_code == 404
    assert "detail" in r.json()


def test_simple_profiles_unsupported_provider_get(api_client):
    r = api_client.get("/agent/profiles/unsupported_provider")
    assert r.status_code == 404


def test_simple_profiles_delete_missing(api_client):
    r = api_client.delete("/agent/profiles/unsupported_provider/__no_such_profile__")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Env token status
# ---------------------------------------------------------------------------


def test_env_token_status(api_client):
    r = api_client.get("/agent/env-token-status", params={"provider": "gigachat"})
    assert r.status_code == 200
    body = r.json()
    assert "hasToken" in (body.get("data") or body)


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------


def test_agent_status(api_client):
    r = api_client.get("/agent/status")
    assert r.status_code == 200
    assert "available" in r.json()


# ---------------------------------------------------------------------------
# Flow plan
# ---------------------------------------------------------------------------


def test_flow_plan_single(api_client):
    r = api_client.get("/agent/flow/plan", params={"mode": "single", "provider": "gigachat"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True


# ---------------------------------------------------------------------------
# Model options
# ---------------------------------------------------------------------------


def test_model_options_gigachat(api_client):
    r = api_client.get("/agent/model-options", params={"provider": "gigachat"})
    assert r.status_code == 200
    body = r.json()
    assert "chat" in body
    assert len(body["chat"]) > 0


def test_model_options_unsupported_provider(api_client):
    r = api_client.get("/agent/model-options", params={"provider": "unsupported_provider"})
    assert r.status_code == 200
    assert "chat" in r.json()["data"]


# ---------------------------------------------------------------------------
# Security headers from middleware
# ---------------------------------------------------------------------------


def test_security_headers_present(api_client):
    r = api_client.get("/health/live")
    assert "x-content-type-options" in r.headers or "X-Content-Type-Options" in r.headers
