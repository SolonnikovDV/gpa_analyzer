"""GigaChat SDK lifecycle — authentication, client kwargs, and connection helpers.

This module owns all SDK-level concerns:
  * building credentials from env / UI override
  * constructing GigaChat() kwargs
  * session management (context-manager)
  * connectivity check (is_available)

It does NOT contain any business-logic (SQL generation, token counting etc.);
those live in actions.py.
"""
from __future__ import annotations

import base64
import os
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SCOPE = "GIGACHAT_API_PERS"

# Справочный список для UI и probe-models
CHAT_MODEL_PRIORITY = (
    "GigaChat-2-Max",
    "GigaChat-2-Pro",
    "GigaChat-2",
)
EMBEDDING_MODEL_PRIORITY = (
    "EmbeddingsGigaR",
    "GigaEmbeddings-3B-2025-09",
    "Embeddings-2",
    "Embeddings",
)
DEFAULT_MODEL = CHAT_MODEL_PRIORITY[0]


def _http_timeout() -> float:
    """Единый HTTP-таймаут для SDK (секунды). Диапазон 30–900."""
    for key in ("GIGACHAT_HTTP_TIMEOUT_SEC", "GIGACHAT_TIMEOUT_SEC"):
        raw = os.environ.get(key, "").strip()
        if raw:
            try:
                return max(30.0, min(float(raw.replace(",", ".")), 900.0))
            except (TypeError, ValueError):
                pass
    return 180.0


def resolved_chat_model(model_override: Optional[str] = None) -> str:
    m = (model_override or "").strip() or os.environ.get("GIGACHAT_MODEL", "").strip()
    return m or DEFAULT_MODEL


def resolved_embedding_model(model_override: Optional[str] = None) -> str:
    m = (model_override or "").strip() or os.environ.get("GIGACHAT_EMBEDDING_MODEL", "").strip()
    return m or EMBEDDING_MODEL_PRIORITY[0]


# ---------------------------------------------------------------------------
# Credential builder
# ---------------------------------------------------------------------------

def build_credentials(
    credentials_override: Optional[str] = None,
    client_id_override: Optional[str] = None,
    client_secret_override: Optional[str] = None,
) -> str:
    """Return a Base64-encoded GigaChat OAuth token from the first available source."""
    if (credentials_override or "").strip():
        return (credentials_override or "").strip()
    cid = (client_id_override or "").strip() or os.environ.get("GIGACHAT_CLIENT_ID", "").strip()
    csec = (client_secret_override or "").strip() or os.environ.get("GIGACHAT_CLIENT_SECRET", "").strip()
    if cid and csec:
        return base64.b64encode(f"{cid}:{csec}".encode()).decode()
    return (
        os.environ.get("GIGACHAT_CREDENTIALS")
        or os.environ.get("GIGACHAT_TOKEN")
        or ""
    ).strip()


# ---------------------------------------------------------------------------
# GigaChatClient — thin SDK wrapper
# ---------------------------------------------------------------------------

class GigaChatClient:
    """Thin wrapper around the GigaChat SDK that manages a single session."""

    def __init__(
        self,
        *,
        credentials_override: Optional[str] = None,
        model_override: Optional[str] = None,
        scope_override: Optional[str] = None,
        client_id_override: Optional[str] = None,
        client_secret_override: Optional[str] = None,
        verify_ssl_override: Optional[bool] = None,
    ) -> None:
        credentials = build_credentials(
            credentials_override=credentials_override,
            client_id_override=client_id_override,
            client_secret_override=client_secret_override,
        )
        if not credentials:
            raise RuntimeError(
                "GigaChat не настроен. Задайте ключ в .env (GIGACHAT_CREDENTIALS) или в форме."
            )

        model = resolved_chat_model(model_override)
        scope = (scope_override or "").strip() or os.environ.get("GIGACHAT_SCOPE", "").strip() or DEFAULT_SCOPE

        if verify_ssl_override is not None:
            verify_ssl = verify_ssl_override
        else:
            verify_ssl = os.environ.get("GIGACHAT_VERIFY_SSL_CERTS", "false").strip().lower() in ("1", "true", "yes")

        self._kwargs: Dict[str, Any] = {
            "credentials": credentials,
            "model": model,
            "scope": scope,
            "verify_ssl_certs": verify_ssl,
            "timeout": _http_timeout(),
        }
        self._giga: Any = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self):
        from gigachat import GigaChat  # type: ignore[import]

        self._giga = GigaChat(**self._kwargs).__enter__()
        return self._giga

    def __exit__(self, *args):
        if self._giga is not None:
            try:
                self._giga.__exit__(*args)
            except Exception:
                pass
            self._giga = None

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def call(self, fn):
        """Open a session, run fn(giga), close session, return result."""
        with self as giga:
            return fn(giga)

    @staticmethod
    def is_available(credentials_override: Optional[str] = None) -> bool:
        """Quick check whether GigaChat SDK is importable and credentials exist."""
        try:
            from gigachat import GigaChat  # noqa: F401
        except ImportError:
            return False
        return bool(build_credentials(credentials_override))

    @staticmethod
    def kwargs_from_env(
        credentials_override: Optional[str] = None,
        model_override: Optional[str] = None,
        scope_override: Optional[str] = None,
        **kw,
    ) -> Dict[str, Any]:
        """Return kwargs dict suitable for GigaChat(**kwargs) — for callers that manage the SDK directly."""
        credentials = build_credentials(credentials_override)
        if not credentials:
            return {}
        model = resolved_chat_model(model_override)
        scope = (scope_override or "").strip() or os.environ.get("GIGACHAT_SCOPE", "").strip() or DEFAULT_SCOPE
        verify_ssl = os.environ.get("GIGACHAT_VERIFY_SSL_CERTS", "false").strip().lower() in ("1", "true", "yes")
        return {
            "credentials": credentials,
            "model": model,
            "scope": scope,
            "verify_ssl_certs": verify_ssl,
            "timeout": _http_timeout(),
            **kw,
        }
