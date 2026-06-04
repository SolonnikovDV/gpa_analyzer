"""Выбор одной чат-/embedding-модели GigaChat и вспомогательные утилиты."""

from modules.agents.gigachat_agent import (
    CHAT_MODEL_PRIORITY,
    DEFAULT_MODEL,
    EMBEDDING_MODEL_PRIORITY,
    _exception_http_status,
    _gigachat_http_timeout_seconds,
    _resolved_chat_model,
    _resolved_embedding_model,
)


class _Resp:
    __slots__ = ("status_code",)

    def __init__(self, status_code: int):
        self.status_code = status_code


def test_chat_priority_starts_with_max():
    assert CHAT_MODEL_PRIORITY[0] == "GigaChat-2-Max"
    assert CHAT_MODEL_PRIORITY[-1] == "GigaChat-2"
    assert len(CHAT_MODEL_PRIORITY) == 3


def test_embedding_priority_starts_with_gigar():
    assert EMBEDDING_MODEL_PRIORITY[0] == "EmbeddingsGigaR"
    assert EMBEDDING_MODEL_PRIORITY[-1] == "Embeddings"


def test_resolved_chat_model_override(monkeypatch):
    monkeypatch.delenv("GIGACHAT_MODEL", raising=False)
    assert _resolved_chat_model("GigaChat-2-Pro") == "GigaChat-2-Pro"


def test_resolved_chat_model_env(monkeypatch):
    monkeypatch.setenv("GIGACHAT_MODEL", "GigaChat-2")
    assert _resolved_chat_model(None) == "GigaChat-2"


def test_resolved_chat_model_default(monkeypatch):
    monkeypatch.delenv("GIGACHAT_MODEL", raising=False)
    assert _resolved_chat_model(None) == DEFAULT_MODEL


def test_resolved_chat_override_beats_env(monkeypatch):
    monkeypatch.setenv("GIGACHAT_MODEL", "GigaChat-2")
    assert _resolved_chat_model("GigaChat-2-Pro") == "GigaChat-2-Pro"


def test_resolved_embedding_model_env(monkeypatch):
    monkeypatch.setenv("GIGACHAT_EMBEDDING_MODEL", "Embeddings-2")
    assert _resolved_embedding_model(None) == "Embeddings-2"


def test_resolved_embedding_model_default(monkeypatch):
    monkeypatch.delenv("GIGACHAT_EMBEDDING_MODEL", raising=False)
    assert _resolved_embedding_model(None) == EMBEDDING_MODEL_PRIORITY[0]


def test_gigachat_http_timeout_defaults_and_env(monkeypatch):
    monkeypatch.delenv("GIGACHAT_HTTP_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("GIGACHAT_TIMEOUT_SEC", raising=False)
    assert _gigachat_http_timeout_seconds() == 180.0
    monkeypatch.setenv("GIGACHAT_TIMEOUT_SEC", "120")
    assert _gigachat_http_timeout_seconds() == 120.0
    monkeypatch.setenv("GIGACHAT_HTTP_TIMEOUT_SEC", "240")
    assert _gigachat_http_timeout_seconds() == 240.0


def test_exception_http_status_nested():
    class Inner(Exception):
        pass

    inner = Inner("x")
    inner.response = _Resp(402)

    class Outer(Exception):
        pass

    outer = Outer("wrap")
    outer.__cause__ = inner
    assert _exception_http_status(outer) == 402
