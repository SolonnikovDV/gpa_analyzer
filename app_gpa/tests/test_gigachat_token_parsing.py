"""Разбор ответов POST /tokens/count и GET /balance (контракт GigaChat REST / SDK)."""

from agent.gigachat_agent import _parse_get_balance_response, normalize_tokens_count_response


def test_normalize_tokens_count_list_like_rest():
    raw = [
        {"object": "tokens", "tokens": 5, "characters": 20},
        {"object": "tokens", "tokens": 3, "characters": 12},
    ]
    out = normalize_tokens_count_response(raw, model_fallback="GigaChat")
    assert out["total"] == 8
    assert len(out["per_input"]) == 2
    assert out["per_input"][0]["tokens"] == 5
    assert out["per_input"][0]["characters"] == 20
    assert out["model"] == "GigaChat"


def test_normalize_tokens_count_wrapped_data():
    out = normalize_tokens_count_response(
        {"model": "GigaChat-Pro", "data": [{"tokens": 10, "characters": 40}]},
    )
    assert out["total"] == 10
    assert out["model"] == "GigaChat-Pro"


def test_normalize_tokens_count_sdk_tokens_wrapper():
    """OpenAPI JS: response.tokens[0].tokens — обёртка с полем tokens (массив)."""
    out = normalize_tokens_count_response(
        {
            "model": "GigaChat",
            "tokens": [
                {"object": "tokens", "tokens": 7, "characters": 36},
            ],
        },
    )
    assert out["total"] == 7
    assert out["model"] == "GigaChat"
    assert out["per_input"][0]["tokens"] == 7


def test_parse_balance_usage_value():
    balance_obj = {
        "balance": [
            {"usage": "GigaChat API", "value": 125000},
            {"usage": "Embeddings", "value": 5000},
        ]
    }
    total_all, total_chat, rows = _parse_get_balance_response(balance_obj)
    assert total_all == 130000
    assert total_chat == 125000
    assert len(rows) == 2
    assert rows[0]["usage"] == "GigaChat API"
    assert rows[0]["tokens"] == 125000
    assert rows[0]["value"] == 125000
    assert rows[0]["model"] == "GigaChat API"


def test_parse_balance_only_embeddings_falls_back_to_total():
    balance_obj = {
        "balance": [
            {"usage": "Embeddings", "value": 999},
        ]
    }
    total_all, total_chat, rows = _parse_get_balance_response(balance_obj)
    assert total_all == 999
    assert total_chat == 999
    assert len(rows) == 1
