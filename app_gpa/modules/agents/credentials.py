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
from typing import Dict, Optional

_B64_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")

SUPPORTED_PROVIDERS = ("gigachat",)


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


def _value_and_key_from_env_file(keys: tuple[str, ...]) -> tuple[Optional[str], Optional[str]]:
    """Return first matching value and key from .env file."""
    for ln in _read_env_file_lines():
        for key in keys:
            prefix = f"{key}="
            if ln.startswith(prefix):
                val = ln[len(prefix):].strip().strip('"').strip("'")
                if val:
                    return val, key
    return None, None


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


def _value_and_key_from_key_prefix(prefixes: tuple[str, ...]) -> tuple[Optional[str], Optional[str]]:
    """Return first matching value and key from .key file."""
    for ln in _read_key_file_lines():
        for prefix in prefixes:
            if ln.startswith(prefix):
                val = ln.split("=", 1)[1].strip()
                if val:
                    key_name = prefix.rstrip("=")
                    return val, key_name
        # bare base64 token — GigaChat legacy format
        if len(ln) >= 32 and all(c in _B64_CHARS for c in ln) and prefixes[0].startswith("GIGACHAT"):
            return ln, "GIGACHAT_BARE_BASE64"
    return None, None


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
    return resolve_credentials_with_source(provider=provider, override=override).get("value")


def resolve_credentials_with_source(
    provider: Optional[str] = None,
    override: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Resolve credentials with diagnostics about source and key.

    Returns:
        {
            "value": <token_or_none>,
            "source": "override|env_file|key_file|os_env|derived_client_secret|none",
            "key": <matched key name or None>
        }
    """
    if override and str(override).strip():
        return {"value": str(override).strip(), "source": "override", "key": "manual_input"}
    p = normalize_provider(provider)

    provider_keys: Dict[str, Dict[str, tuple[str, ...]]] = {
        "gigachat": {
            "env": ("GIGACHAT_TOKEN", "GIGACHAT_CREDENTIALS"),
            "key": ("GIGACHAT_TOKEN=", "GIGACHAT_CREDENTIALS="),
            "os": ("GIGACHAT_CREDENTIALS", "GIGACHAT_TOKEN"),
        },
    }

    def _from_os_env(keys: tuple[str, ...]) -> tuple[Optional[str], Optional[str]]:
        for key in keys:
            val = (os.environ.get(key) or "").strip()
            if val:
                return val, key
        return None, None

    def _resolve_from_config(conf: Dict[str, tuple[str, ...]]) -> Dict[str, Optional[str]]:
        env_val, env_key = _value_and_key_from_env_file(conf["env"])
        if env_val:
            return {"value": env_val, "source": "env_file", "key": env_key}
        key_val, key_key = _value_and_key_from_key_prefix(conf["key"])
        if key_val:
            return {"value": key_val, "source": "key_file", "key": key_key}
        os_val, os_key = _from_os_env(conf["os"])
        if os_val:
            return {"value": os_val, "source": "os_env", "key": os_key}
        return {"value": None, "source": "none", "key": None}

    resolved = _resolve_from_config(provider_keys[p])
    if resolved.get("value"):
        return resolved
    if p == "gigachat":
        derived = _gigachat_from_client_secret()
        if derived:
            return {
                "value": derived,
                "source": "derived_client_secret",
                "key": "GIGACHAT_CLIENT_ID/GIGACHAT_CLIENT_SECRET",
            }
    return {"value": None, "source": "none", "key": None}


def _gigachat_from_client_secret() -> Optional[str]:
    cid = os.environ.get("GIGACHAT_CLIENT_ID", "").strip()
    csec = os.environ.get("GIGACHAT_CLIENT_SECRET", "").strip()
    if cid and csec:
        import base64
        return base64.b64encode(f"{cid}:{csec}".encode()).decode()
    return None


def credentials_configured(provider: Optional[str] = None) -> bool:
    return bool(resolve_credentials(provider))
