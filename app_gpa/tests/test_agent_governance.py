"""Tests for repo-embedded agent governance."""
from modules.agents.governance.loader import governance_public_summary, load_manifest, load_role_brief
from modules.agents.governance.prompt_composer import compose_team_brief
from modules.agents.governance.registry import roles_for_step


def test_manifest_loads():
    m = load_manifest()
    assert m.get("team_id") == "gpa-agent-team"
    assert "generate_sql" in (m.get("track_steps") or {})


def test_greenplum_stack_includes_gp_developer():
    roles = roles_for_step("synthesize_plan", "greenplum")
    assert "greenplum_developer" in roles
    assert "dba" in roles


def test_compose_team_brief_contains_step():
    brief = compose_team_brief("generate_sql", "greenplum")
    assert "generate_sql" in brief
    assert "greenplum" in brief


def test_role_brief_exists():
    assert "Greenplum" in load_role_brief("greenplum_developer")


def test_governance_public_summary():
    s = governance_public_summary("greenplum")
    assert s["team_id"] == "gpa-agent-team"
    assert "gigachat" in s["providers"]
