from modules.agents.orchestrator import AgentOrchestrator


def test_orchestrator_enrich_prompt():
    orch = AgentOrchestrator(provider="gigachat", stack="greenplum")
    out = orch.enrich_prompt("generate_sql", "SELECT 1")
    assert "GPA Agent Team" in out
    assert "SELECT 1" in out
