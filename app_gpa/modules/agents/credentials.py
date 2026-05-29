"""Unified agent credentials from .env, .key, and env vars.

Resolution priority (per provider):
  1. UI/call-site override (explicit token passed by caller)
  2. .env file  (direct parse, highest-priority file source)
  3. .key file  (legacy project-specific credential store)
  4. os.environ (system env, CI/CD, already-loaded dotenv fallback)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

_B64_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")

SUPPORTED_PROVIDERS = ("gigachat", "deepseek", "groq", "openrouter")


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _project_roots() -> list[Path]:
    here = Path(__file__).resolve()
    # credentials.py lives at app_gpa/modules/agents/credentials.py
    # → parent = agents/, parent.parent = modules/, parent.parent.parent = app_gpa/
    app_gpa = here.parent.parent.parent
    project = app_gpa.parent
    return [project, app_gpa]


# ---------------------------------------------------------------------------
# .env file reader (direct parse, no side-effects on os.environ)
# ---------------------------------------------------------------------------

def _read_env_file_lines() -> list[str]:
    """Read non-comment, non-empty lines from the first .env found."""
    for root in _project_roots():
        env_path = root / ".env"
        if not env_path.is_file():
            continue
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
            return [
                ln.strip()
                for ln in lines
                if ln.strip() and not ln.strip().startswith("#")
            ]
        except OSError:
            continue
    return []


def _value_from_env_file(keys: tuple[str, ...]) -> Optional[str]:
    """Return first matching key value from .env file (strips surrounding quotes)."""
    for ln in _read_env_file_lines():
        for key in keys:
            prefix = f"{key}="
            if ln.startswith(prefix):
                val = ln[len(prefix):].strip().strip('"').strip("'")
                if val:
                    return val
    return None


# ---------------------------------------------------------------------------
# .key file reader (legacy format: KEY=value or bare base64 for GigaChat)
# ---------------------------------------------------------------------------

def _read_key_file_lines() -> list[str]:
    for root in _project_roots():
        key_path = root / ".key"
        if not key_path.is_file():
            continue
        try:
            return [ln.strip() for ln in key_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        except OSError:
            continue
    return []


def _value_from_key_prefix(prefixes: tuple[str, ...]) -> Optional[str]:
    for ln in _read_key_file_lines():
        for prefix in prefixes:
            if ln.startswith(prefix):
                val = ln.split("=", 1)[1].strip()
                if val:
                    return val
        # bare base64 token — GigaChat legacy format
        if len(ln) >= 32 and all(c in _B64_CHARS for c in ln) and prefixes[0].startswith("GIGACHAT"):
            return ln
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_provider(provider: Optional[str]) -> str:
    p = (provider or "gigachat").strip().lower()
    return p if p in SUPPORTED_PROVIDERS else "gigachat"


def resolve_credentials(
    provider: Optional[str] = None,
    override: Optional[str] = None,
) -> Optional[str]:
    """Resolve credentials: UI override → .env → .key → os.environ."""
    if override and str(override).strip():
        return str(override).strip()
    p = normalize_provider(provider)
    if p == "deepseek":
        return (
            _value_from_env_file(("DEEPSEEK_TOKEN", "DEEPSEEK_API_KEY"))
            or _value_from_key_prefix(("DEEPSEEK_TOKEN=", "DEEPSEEK_API_KEY="))
            or os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("DEEPSEEK_TOKEN")
        )
    if p == "groq":
        return (
            _value_from_env_file(("GROQ_API_KEY", "GROQ_TOKEN"))
            or _value_from_key_prefix(("GROQ_API_KEY=", "GROQ_TOKEN="))
            or os.environ.get("GROQ_API_KEY")
            or os.environ.get("GROQ_TOKEN")
        )
    if p == "openrouter":
        return (
            _value_from_env_file(("OPENROUTER_API_KEY", "OPENROUTER_TOKEN"))
            or _value_from_key_prefix(("OPENROUTER_API_KEY=", "OPENROUTER_TOKEN="))
            or os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("OPENROUTER_TOKEN")
        )
    return (
        _value_from_env_file(("GIGACHAT_TOKEN", "GIGACHAT_CREDENTIALS"))
        or _value_from_key_prefix(("GIGACHAT_TOKEN=", "GIGACHAT_CREDENTIALS="))
        or os.environ.get("GIGACHAT_CREDENTIALS")
        or os.environ.get("GIGACHAT_TOKEN")
        or _gigachat_from_client_secret()
    )


def _gigachat_from_client_secret() -> Optional[str]:
    cid = os.environ.get("GIGACHAT_CLIENT_ID", "").strip()
    csec = os.environ.get("GIGACHAT_CLIENT_SECRET", "").strip()
    if cid and csec:
        import base64
        return base64.b64encode(f"{cid}:{csec}".encode()).decode()
    return None


def credentials_configured(provider: Optional[str] = None) -> bool:
    return bool(resolve_credentials(provider))
