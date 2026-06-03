"""Integration tests: agent track API, pure-agent discovery, governance metadata."""
from __future__ import annotations

import json
import time
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
pytest.importorskip("fastapi", reason="fastapi not installed; skipping integration API tests", exc_type=ImportError)

from fastapi import FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware
from fastapi.testclient import TestClient

import webapp
from api.app_factory import create_api_app
from modules.agents.providers.base import ChatMessage, ChatResult, ProviderInfo
from modules.analysis.analysis_orchestrator import AnalysisOrchestrator
from modules.analysis.job_contracts import JOB_STATUS_DONE, JOB_STATUS_TABLES_DISCOVERED
from modules.analysis.job_service import JobService
from modules.analysis.job_store import SQLiteJobStore
from modules.analysis.performance_monitor import PerformanceMonitor
from modules.analysis.runtime_preset_store import SQLiteRuntimePresetStore


SAMPLE_DDL = """
CREATE OR REPLACE FUNCTION public.f_test(p_date date)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO public.t1 SELECT 1;
END;
$$;
"""

AGENT_BLOCKS_RESPONSE = {
    "blocks": [{"type": "INSERT", "sql": "INSERT INTO public.t1 SELECT 1"}],
    "objects": ["public.t1"],
    "function_params": ["p_date"],
    "variables": [],
}

SAMPLE_PLAN = {
    "Plan": {
        "Node Type": "Seq Scan",
        "Relation Name": "t1",
        "Schema": "public",
        "Plan Rows": 10000,
        "Plan Width": 64,
        "Total Cost": 100.0,
        "Plans": [],
    }
}

DISCOVERY_PAYLOAD: Dict[str, Any] = {
    "stack": "greenplum",
    "ddl": SAMPLE_DDL,
    "analysis_mode": "hybrid",
    "plan_source": "agent",
    "use_db_connection": False,
    "agent_credentials": "sk-test",
    "agent_scope": "GIGACHAT_API_PERS",
    "agent_provider": "gigachat",
    "agent_chat_model": "GigaChat-2",
    "agent_description": "test function",
    "segments": 120,
    "ram_per_seg_gb": 153.6,
}


def _patch_pure_agent_mocks(monkeypatch):
    monkeypatch.setattr(
        "modules.agents.gigachat_agent.get_blocks_and_objects_from_ddl",
        lambda *args, **kwargs: dict(AGENT_BLOCKS_RESPONSE),
    )
    monkeypatch.setattr("modules.agents.agent_cache_db.get_state", lambda *a, **k: None)
    monkeypatch.setattr("modules.agents.agent_cache_db.set_state", lambda *a, **k: None)
    monkeypatch.setattr("modules.agents.agent_cache_db.get_plan", lambda *a, **k: None)
    monkeypatch.setattr("modules.agents.agent_cache_db.set_plan", lambda *a, **k: None)


@pytest.fixture()
def client(monkeypatch, tmp_path):
    preset_store = SQLiteRuntimePresetStore(str(tmp_path / "presets.sqlite3"))
    job_store = SQLiteJobStore(str(tmp_path / "jobs.sqlite3"))
    job_service = JobService(job_store, {}, {})

    monkeypatch.setattr(webapp, "_preset_store", preset_store)
    perf_monitors: dict = {}
    monkeypatch.setattr(webapp, "_job_service", job_service)
    monkeypatch.setattr(webapp, "_performance_monitors", perf_monitors)
    monkeypatch.setattr(
        webapp,
        "_analysis_orchestrator",
        AnalysisOrchestrator(job_service, perf_monitors, PerformanceMonitor),
    )
    monkeypatch.setattr(webapp, "_persistence", SimpleNamespace(db_path=str(tmp_path / "health.sqlite3")))

    root = FastAPI(title="GPA Test", docs_url="/api/docs", openapi_url="/api/openapi.json")
    root.mount("/api", create_api_app())
    root.mount("/", WSGIMiddleware(webapp.app))
    with TestClient(root) as test_client:
        yield test_client, job_service


def test_api_governance_summary(client):
    test_client, _ = client
    response = test_client.get("/api/agent/governance?stack=greenplum")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    data = payload["data"]
    assert data["team_id"] == "gpa-agent-team"
    assert "generate_sql" in data["track_steps"]
    assert "gigachat" in data["providers"]


def test_api_providers_contract(client):
    test_client, _ = client
    response = test_client.get("/api/agent/providers")
    payload = response.get_json()
    assert response.status_code == 200
    ids = [p["id"] for p in payload["data"]["providers"]]
    assert "gigachat" in ids
    assert "gigachat" in ids


def test_status_exposes_agent_and_governance_fields(client):
    test_client, job_service = client
    job_service.create_job(
        "job-agent-meta",
        {
            "status": JOB_STATUS_TABLES_DISCOVERED,
            "stack": "greenplum",
            "analysis_mode": "hybrid",
            "use_db_connection": False,
            "agent_provider": "gigachat",
            "agent_chat_model": "GigaChat-2",
            "discovery_result": {"use_agent_path": True, "blocks_count": 1},
        },
    )
    response = test_client.get("/status/job-agent-meta")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["agent_provider"] == "gigachat"
    assert payload["governance_team_id"] == "gpa-agent-team"
    assert payload["governance_version"] == "1.0.0"
    assert payload["discovery"]["use_agent_path"] is True


def test_pure_agent_discovery_gigachat_mocked(client, monkeypatch):
    _, job_service = client
    job_id = "disc-gigachat-1"
    job_service.create_job(
        job_id,
        {
            "status": "running",
            "stack": "greenplum",
            "analysis_mode": "hybrid",
            "use_db_connection": False,
        },
    )

    _patch_pure_agent_mocks(monkeypatch)

    webapp._run_discovery_job(job_id, dict(DISCOVERY_PAYLOAD))

    job = job_service.get_job(job_id)
    assert job is not None
    assert job["status"] == JOB_STATUS_TABLES_DISCOVERED
    discovery = job.get("discovery_result") or {}
    assert discovery.get("use_agent_path") is True
    assert discovery.get("blocks_count", 0) >= 1
    assert "public.t1" in (discovery.get("discovered_tables") or {})


def test_pure_agent_analysis_gigachat_mocked(client, monkeypatch):
    """E2E шаг 3: discovery → analysis с agent plan (DeepSeek mocked)."""
    _, job_service = client
    job_id = "analysis-gigachat-1"
    job_service.create_job(
        job_id,
        {
            "status": "running",
            "stack": "greenplum",
            "analysis_mode": "hybrid",
            "plan_source": "agent",
            "use_db_connection": False,
            **{k: DISCOVERY_PAYLOAD[k] for k in (
                "agent_credentials", "agent_scope", "agent_provider",
                "agent_chat_model", "segments", "ram_per_seg_gb",
            )},
        },
    )
    _patch_pure_agent_mocks(monkeypatch)

    def fake_synthesize(query, objects, **kwargs):
        assert kwargs.get("provider") == "gigachat"
        assert kwargs.get("stack") == "greenplum"
        return dict(SAMPLE_PLAN)

    monkeypatch.setattr("modules.agents.gigachat_agent.synthesize_plan_for_query", fake_synthesize)

    webapp._run_discovery_job(job_id, dict(DISCOVERY_PAYLOAD))

    job = job_service.get_job(job_id)
    assert job["status"] == JOB_STATUS_TABLES_DISCOVERED

    analysis_payload = {
        "params": ["'2024-01-01'"],
        "user_sizes": {"public.t1": 10000},
    }
    webapp._run_analysis_job(job_id, analysis_payload)

    job = job_service.get_job(job_id)
    assert job["status"] == JOB_STATUS_DONE
    result = job.get("result") or {}
    assert result.get("analyzed_blocks", 0) >= 1
    assert result.get("agent_provider") == "gigachat"
    assert result.get("risk")


def test_track_generate_gigachat_with_review_mocked(monkeypatch):
    from modules.agents.orchestrator import AgentOrchestrator
    from modules.agents.track import generate_sql

    calls: List[str] = []

    def fake_chat(self, step_id, user_prompt, *, system_extra=None):
        calls.append(step_id)
        if step_id == "analyze_description":
            return ChatResult(
                text=json.dumps({"intent": "function", "context_sufficient": True, "warning": None}),
                provider="gigachat",
                model="GigaChat-2",
            )
        if step_id == "generate_sql":
            return ChatResult(text="SELECT 1;", provider="gigachat", model="GigaChat-2")
        if step_id == "revise_sql":
            return ChatResult(text="SELECT 1;", provider="gigachat", model="GigaChat-2")
        return ChatResult(text="", provider="gigachat", model="GigaChat-2")

    monkeypatch.setattr(AgentOrchestrator, "chat", fake_chat)

    out = generate_sql(
        "simple query",
        provider="gigachat",
        stack="greenplum",
        credentials_override="sk-test",
        with_review=True,
        code_revision_pass=True,
    )
    assert out["provider"] == "gigachat"
    assert "SELECT 1" in out["sql_or_ddl"]
    assert "generate_sql" in calls
    assert out.get("code_revision_ran") is True


def test_track_generate_gigachat_multi_agent_mocked(monkeypatch):
    from modules.agents.orchestrator import AgentOrchestrator
    from modules.agents.track import generate_sql

    def fake_chat(self, step_id, user_prompt, *, system_extra=None):
        return ChatResult(
            text="CONSENSUS: SELECT 42;",
            provider="gigachat",
            model="GigaChat-2",
        )

    monkeypatch.setattr(AgentOrchestrator, "chat", fake_chat)

    out = generate_sql(
        "count rows",
        provider="gigachat",
        stack="greenplum",
        credentials_override="test-creds",
        multi_agent=True,
    )
    assert out["provider"] == "gigachat"
    assert out.get("multi_agent") is True
    assert "42" in out["sql_or_ddl"]


def test_orchestrator_multi_agent_consensus(monkeypatch):
    from modules.agents.orchestrator import AgentOrchestrator

    round_idx = {"n": 0}

    class FakeProvider:
        id = "gigachat"

        def info(self):
            return ProviderInfo(
                id="gigachat",
                label="GigaChat",
                default_chat_model="GigaChat-2",
                supports_embeddings=False,
            )

        def validate(self, credentials, **kwargs):
            return None

        def chat(self, messages, *, credentials, model=None, **kwargs):
            round_idx["n"] += 1
            if round_idx["n"] < 3:
                text = f"Round {round_idx['n']}: needs review"
            else:
                text = "CONSENSUS: SELECT 1"
            return ChatResult(text=text, provider="gigachat", model=model or "GigaChat-2")

    monkeypatch.setattr("modules.agents.orchestrator.get_provider", lambda _pid: FakeProvider())
    monkeypatch.setenv("GPA_MULTI_AGENT_ENABLED", "1")

    orch = AgentOrchestrator(
        provider="gigachat",
        stack="greenplum",
        credentials_override="sk-test",
        multi_agent=True,
    )
    result = orch.chat("generate_sql", "SELECT 1")
    assert "CONSENSUS" in (result.text or "").upper()
    assert round_idx["n"] >= 2
