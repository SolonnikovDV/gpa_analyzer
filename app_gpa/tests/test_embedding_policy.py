from modules.agents.embedding_policy import cache_mode_label, supports_semantic_cache


def test_deepseek_no_semantic_cache():
    # Unsupported providers are normalized to active provider policy.
    assert supports_semantic_cache("deepseek") is True
    assert cache_mode_label("deepseek") == "exact+semantic"


def test_gigachat_semantic_cache():
    assert supports_semantic_cache("gigachat") is True
    assert cache_mode_label("gigachat") == "exact+semantic"
