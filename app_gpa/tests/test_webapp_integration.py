from types import SimpleNamespace

import pytest
pytest.importorskip("fastapi", reason="fastapi not installed; skipping webapp integration tests", exc_type=ImportError)

from fastapi import FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware
from fastapi.testclient import TestClient

import webapp
from api.app_factory import create_api_app
from modules.analysis.job_contracts import JOB_STATUS_DONE, JOB_STATUS_TABLES_DISCOVERED
from modules.analysis.job_service import JobService
from modules.analysis.job_store import SQLiteJobStore
from modules.analysis.runtime_preset_store import SQLiteRuntimePresetStore


@pytest.fixture()
def client(monkeypatch, tmp_path):
    preset_store = SQLiteRuntimePresetStore(str(tmp_path / "presets.sqlite3"))
    job_store = SQLiteJobStore(str(tmp_path / "jobs.sqlite3"))
    job_service = JobService(job_store, {}, {})

    monkeypatch.setattr(webapp, "_preset_store", preset_store)
    monkeypatch.setattr(webapp, "_job_service", job_service)
    monkeypatch.setattr(webapp, "_performance_monitors", {})
    monkeypatch.setattr(webapp, "_persistence", SimpleNamespace(db_path=str(tmp_path / "health.sqlite3")))

    root = FastAPI(title="GPA Test", docs_url="/api/docs", openapi_url="/api/openapi.json")
    root.mount("/api", create_api_app())
    root.mount("/", WSGIMiddleware(webapp.app))
    with TestClient(root) as test_client:
        yield test_client, job_service


def test_runtime_descriptor_returns_unified_contract(client):
    test_client, _ = client

    response = test_client.post("/api/runtime/descriptor", json={"stack": "spark", "scenario": "logic"})

    payload = response.json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["stack"] == "spark"
    assert payload["data"]["descriptor"]["stack"] == "spark"
    assert "supported_stacks" in payload


def test_runtime_presets_crud_flow(client):
    test_client, _ = client

    create_response = test_client.post(
        "/api/runtime-presets",
        json={"stack": "greenplum", "kind": "metadata", "name": "preset-1", "value": "{\"v\":1}"},
    )
    created = create_response.json()
    assert create_response.status_code == 200
    assert created["ok"] is True
    assert created["preset"]["name"] == "preset-1"

    list_response = test_client.get("/api/runtime-presets?stack=greenplum&kind=metadata")
    listed = list_response.json()
    assert list_response.status_code == 200
    assert listed["ok"] is True
    assert listed["items"][0]["name"] == "preset-1"

    delete_response = test_client.request(
        "DELETE",
        "/api/runtime-presets",
        json={"stack": "greenplum", "kind": "metadata", "name": "preset-1"},
    )
    deleted = delete_response.json()
    assert delete_response.status_code == 200
    assert deleted["ok"] is True
    assert deleted["deleted"] is True


def test_runtime_presets_validation_error_uses_standard_contract(client):
    test_client, _ = client

    response = test_client.post("/api/runtime-presets", json={"stack": "greenplum", "value": "{}"})

    payload = response.json()
    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["error_code"] == "preset_kind_required"


def test_runtime_test_for_spark_returns_ok_contract(client):
    test_client, _ = client

    response = test_client.post("/api/runtime/test", json={"stack": "spark", "scenario": "logic", "master_url": "local"})

    payload = response.json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["stack"] == "spark"
    assert payload["data"]["runtime_note"]


def test_status_and_details_endpoints_return_unified_contract(client):
    test_client, job_service = client
    job_service.create_job(
        "job-1",
        {
            "status": JOB_STATUS_DONE,
            "stack": "greenplum",
            "analysis_mode": "logic",
            "use_db_connection": True,
            "result": {
                "function": "f_test",
                "analyzed_blocks": 2,
                "total_memory_gb": 1.5,
                "antipattern_added_gb": 0.2,
                "estimated_time_sec": 12,
                "risk": "medium",
            },
        },
    )

    status_response = test_client.get("/status/job-1")
    status_payload = status_response.json()
    assert status_response.status_code == 200
    assert status_payload["ok"] is True
    assert status_payload["status"] == JOB_STATUS_DONE
    assert status_payload["summary"]["function"] == "f_test"

    details_response = test_client.get("/details/job-1")
    details_payload = details_response.json()
    assert details_response.status_code == 200
    assert details_payload["ok"] is True
    assert details_payload["function"] == "f_test"
    assert details_payload["data"]["function"] == "f_test"


def test_status_not_found_returns_standard_error(client):
    test_client, _ = client

    response = test_client.get("/status/missing-job")

    payload = response.json()
    assert response.status_code == 404
    assert payload["ok"] is False
    assert payload["error_code"] == "job_not_found"
    assert payload["job_status"] == "not_found"


def test_performance_endpoint_returns_monitor_stats(client, monkeypatch):
    test_client, _ = client

    class StubMonitor:
        def get_stats(self):
            return {"cpu_percent": 10, "memory_mb": 128}

    monkeypatch.setattr(webapp, "_performance_monitors", {"job-1": StubMonitor()})

    response = test_client.get("/performance/job-1")

    payload = response.json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["cpu_percent"] == 10
    assert payload["data"]["memory_mb"] == 128


def test_status_tables_discovered_includes_discovery_payload(client):
    test_client, job_service = client
    job_service.create_job(
        "job-2",
        {
            "status": JOB_STATUS_TABLES_DISCOVERED,
            "stack": "greenplum",
            "analysis_mode": "logic",
            "use_db_connection": True,
            "discovery_result": {"use_agent_path": False, "tables": ["public.t1"]},
        },
    )

    response = test_client.get("/status/job-2")

    payload = response.json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["discovery"]["tables"] == ["public.t1"]


def test_request_id_is_exposed_in_response_headers(client):
    test_client, _ = client

    response = test_client.get("/api/cache/baseline", headers={"X-Request-ID": "req-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-123"


def test_health_live_is_public_and_returns_live_status(client):
    test_client, _ = client

    response = test_client.get("/health/live")

    payload = response.json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["status"] == "live"
    assert payload["data"]["checks"]["app"]["ok"] is True


def test_health_ready_returns_readiness_checks(client):
    test_client, _ = client

    response = test_client.get("/health/ready")

    payload = response.json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["status"] == "ready"
    assert payload["checks"]["sqlite"]["ok"] is True
