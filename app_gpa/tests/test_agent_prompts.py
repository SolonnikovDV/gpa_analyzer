"""Тесты шаблонов промптов агента."""

from agent.agent_prompts import get_prompt


def test_revise_sql_prompt_escapes_braces_in_user_sql():
    sql = "SELECT json_build_object('a', 1) AS x"
    prompt = get_prompt("revise_sql", sql=sql, description="test")
    assert "json_build_object('a', 1)" in prompt
    assert "{sql}" not in prompt


def test_revise_sql_prompt_includes_description():
    prompt = get_prompt("revise_sql", sql="SELECT 1", description="Сделать витрину")
    assert "Сделать витрину" in prompt
    assert "SELECT 1" in prompt
