import os

from modules.agents.governance.multi_agent_policy import (
    MultiAgentSession,
    is_multi_agent_enabled,
    next_debate_mode,
    should_continue_debate,
)
from modules.agents.governance.prompt_composer import compose_debate_instruction


def test_multi_agent_disabled_by_default():
    assert is_multi_agent_enabled() is False


def test_multi_agent_env_override(monkeypatch):
    monkeypatch.setenv("GPA_MULTI_AGENT_ENABLED", "1")
    assert is_multi_agent_enabled() is True
    monkeypatch.setenv("GPA_MULTI_AGENT_ENABLED", "0")
    assert is_multi_agent_enabled() is False


def test_debate_modes_cycle():
    assert next_debate_mode(0) == "review"
    assert next_debate_mode(1) == "challenge"
    assert next_debate_mode(2) == "synthesize"


def test_should_stop_when_disabled():
    session = MultiAgentSession(step_id="generate_sql", stack="greenplum", provider="gigachat")
    assert should_continue_debate(session, multi_agent_override=False) is False


def test_should_stop_at_max_rounds(monkeypatch):
    monkeypatch.setenv("GPA_MULTI_AGENT_ENABLED", "1")
    session = MultiAgentSession(step_id="generate_sql", stack="greenplum", provider="gigachat")
    session.round_index = 3
    assert should_continue_debate(session) is False


def test_compose_debate_instruction():
    text = compose_debate_instruction("review", "generate_sql", "greenplum", round_index=0)
    assert "review" in text
    assert "CONSENSUS" in text
