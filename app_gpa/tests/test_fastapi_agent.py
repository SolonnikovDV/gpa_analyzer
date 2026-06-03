"""Tests for FastAPI agent flow endpoints."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed; skipping FastAPI tests")

from fastapi.testclient import TestClient

from api.app_factory import create_api_app


@pytest.fixture()
def api_client():
    app = create_api_app()
    return TestClient(app)


def test_flow_plan_single_gigachat(api_client):
    r = api_client.get("/agent/flow/plan", params={"mode": "single", "provider": "gigachat"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["mode"] == "single"
    assert body["slots"][0]["provider_id"] == "gigachat"


def test_flow_plan_multi(api_client):
    r = api_client.get(
        "/agent/flow/plan",
        params={"mode": "multi", "selected_provider_ids": "gigachat,deepseek"},
    )
    body = r.json()
    assert body["ok"] is True
    # Hard-mode runtime normalizes to single provider flow.
    assert body["mode"] == "single"
    assert len(body["slots"]) == 1
    assert body["slots"][0]["provider_id"] == "gigachat"


def test_providers_list(api_client):
    r = api_client.get("/agent/providers")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "providers" in body["data"]
