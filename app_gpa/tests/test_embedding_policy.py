from modules.agents.embedding_policy import cache_mode_label, supports_semantic_cache


def test_unsupported_provider_uses_active_policy():
    assert supports_semantic_cache("unsupported_provider") is True
    assert cache_mode_label("unsupported_provider") == "exact+semantic"


def test_gigachat_semantic_cache():
    assert supports_semantic_cache("gigachat") is True
    assert cache_mode_label("gigachat") == "exact+semantic"
