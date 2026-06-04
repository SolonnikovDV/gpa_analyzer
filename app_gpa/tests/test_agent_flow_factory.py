"""Tests for unified agent flow factory."""
from __future__ import annotations

from modules.agents.flow.factory import build_flow_plan, flow_plan_to_dict
from modules.agents.flow.profile_handlers import get_profile_handler


def test_single_flow_same_steps_for_providers():
    plan = build_flow_plan(mode="single", stack="greenplum", provider="gigachat")
    d = flow_plan_to_dict(plan)
    assert d["mode"] == "single"
    kinds = [s["kind"] for s in d["steps"]]
    assert kinds.count("profile") == 1
    assert kinds[-1] == "ready"
    assert d["slots"][0]["provider_id"] == "gigachat"
    assert "profile_schema" in d["slots"][0]


def test_multi_flow_select_then_profiles():
    plan = build_flow_plan(
        mode="multi",
        stack="greenplum",
        selected_provider_ids=["gigachat"],
    )
    d = flow_plan_to_dict(plan)
    assert d["mode"] == "multi"
    assert d["steps"][0]["kind"] == "select_slots"
    profile_steps = [s for s in d["steps"] if s["kind"] == "profile"]
    assert len(profile_steps) >= 1
    assert profile_steps[0]["slot"]["governance_roles"]
    assert d["multi_agent_policy"]


def test_profile_handlers_share_validate_interface():
    h = get_profile_handler("gigachat")
    schema = h.field_schema()
    assert schema["provider_id"] == "gigachat"
    assert isinstance(schema["fields"], list)
