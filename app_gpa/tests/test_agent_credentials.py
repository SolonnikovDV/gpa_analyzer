from modules.agents.credentials import normalize_provider, resolve_credentials


def test_normalize_provider_defaults_gigachat():
    assert normalize_provider(None) == "gigachat"
    assert normalize_provider("DEEPSEEK") == "deepseek"


def test_resolve_deepseek_from_env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")
    assert resolve_credentials("deepseek") == "sk-test-key"
