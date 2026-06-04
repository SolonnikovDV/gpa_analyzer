"""Починка Invalid \\escape в JSON от агента (SQL с regex внутри строк)."""

import json

import pytest

from modules.agents.gigachat_agent import _parse_first_json, _repair_json_invalid_escapes


def test_repair_regex_escape_in_json_string():
    # Как часто отдаёт LLM: внутри JSON в sql литерал с '\d' без второго слэша для JSON
    bad = '{"blocks":[{"type":"INSERT","sql":"WHERE t ~ \'\\d{4}-\\d\\d\'"}]}'
    with pytest.raises(json.JSONDecodeError):
        json.loads(bad)
    fixed = _repair_json_invalid_escapes(bad)
    data = json.loads(fixed)
    assert data["blocks"][0]["sql"] == "WHERE t ~ '\\d{4}-\\d\\d'"


def test_parse_first_json_applies_repair():
    raw = 'prefix text\n' + r'{"x": "line: \s+ end"}'
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw[raw.find("{") :])
    obj = _parse_first_json(raw)
    assert obj["x"] == r"line: \s+ end"


def test_no_change_to_valid_escapes():
    s = r'{"a": "n:\n t:\t q:\" ok"}'
    assert _repair_json_invalid_escapes(s) == s
    assert _parse_first_json(s)["a"] == 'n:\n t:\t q:" ok'
