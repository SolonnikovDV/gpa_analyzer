from modules.agents.credentials import normalize_provider, resolve_credentials


def test_normalize_provider_defaults_gigachat():
    assert normalize_provider(None) == "gigachat"
    assert normalize_provider("UNSUPPORTED_PROVIDER") == "gigachat"


def test_resolve_unsupported_provider_falls_back_to_gigachat():
    assert resolve_credentials("unsupported_provider") == resolve_credentials("gigachat")
