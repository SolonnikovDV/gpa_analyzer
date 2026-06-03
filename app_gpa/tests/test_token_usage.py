"""Tests for per-provider token usage tracking."""
from __future__ import annotations

from modules.agents.token_usage import fetch_deepseek_balance, get_last_request_usage, record_usage


def test_record_usage_tracks_last_request(monkeypatch):
    calls = []

    def fake_add(provider, pt, ct, tt, sessions):
        calls.append((provider, pt, ct, tt, sessions))

    monkeypatch.setattr("modules.agents.agent_cache_db.add_token_usage_for_provider", fake_add)

    record_usage({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}, provider="deepseek")
    # Unsupported providers are normalized to gigachat.
    last = get_last_request_usage("gigachat")
    assert last == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    assert calls == [("gigachat", 10, 5, 15, 1)]


def test_fetch_deepseek_balance_missing_key(monkeypatch):
    monkeypatch.setattr("modules.agents.token_usage.resolve_credentials", lambda *a, **k: None)
    out = fetch_deepseek_balance(None)
    assert out["ok"] is False
    assert out["balance_source"] == "missing_credentials"


def test_get_token_usage_by_provider(monkeypatch):
    monkeypatch.setattr(
        "modules.agents.token_usage.fetch_deepseek_balance",
        lambda creds: {
            "ok": True,
            "balance_source": "deepseek_user_balance",
            "total_balance": "1.50",
            "currency": "USD",
            "is_available": True,
            "granted_balance": "0",
            "topped_up_balance": "1.50",
        },
    )
    monkeypatch.setattr(
        "modules.agents.token_usage.get_provider_totals",
        lambda p: {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120, "sessions": 3},
    )
    monkeypatch.setattr(
        "modules.agents.agent_cache_db.get_token_usage_totals",
        lambda: {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120, "sessions": 3},
    )
    monkeypatch.setattr(
        "modules.agents.token_usage.get_last_request_usage",
        lambda p=None: {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    )
    monkeypatch.setattr("modules.agents.gigachat_agent._gigachat_client_kwargs", lambda **k: None)

    from modules.agents.gigachat_agent import get_token_usage

    out = get_token_usage(provider="deepseek")
    assert out["provider"] == "gigachat"
    assert out["used"]["total_tokens"] == 120
    assert out["last_request"]["prompt_tokens"] == 10
    assert "total_balance" not in out
    assert out["by_provider"]["deepseek"]["provider"] == "gigachat"
