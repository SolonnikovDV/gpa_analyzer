"""Filesystem paths for the GPA application package."""
from __future__ import annotations

from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = APP_DIR.parent
WEB_DIR = APP_DIR / "web"
WEB_STATIC_DIR = WEB_DIR / "static"
WEB_TEMPLATE_DIRS = (
    WEB_DIR / "templates" / "app",
    WEB_DIR / "templates" / "analysis",
)
CONFIG_DIR = APP_DIR / "config"
VAR_DIR = APP_DIR / "var"
AGENT_CACHE_DIR = VAR_DIR / "agent_cache"
AGENT_PROFILES_PATH = CONFIG_DIR / "agent_profiles.json"
DEEPSEEK_PROFILES_PATH = CONFIG_DIR / "deepseek_profiles.json"
GROQ_PROFILES_PATH = CONFIG_DIR / "groq_profiles.json"
OPENROUTER_PROFILES_PATH = CONFIG_DIR / "openrouter_profiles.json"
SQL_FUNCTION_PROFILES_PATH = CONFIG_DIR / "sql_function_profiles.json"


def simple_provider_profiles_path(provider_id: str):
    """Return Path to <provider_id>_profiles.json in config dir."""
    return CONFIG_DIR / f"{provider_id}_profiles.json"
SQL_FUNCTION_CACHE_PATH = VAR_DIR / "sql_function_cache.json"

# Legacy name used across Flask routes and scripts.
WEBAPP_DIR = str(APP_DIR)


def ensure_runtime_dirs() -> None:
    """Create local runtime directories (not committed to git)."""
    VAR_DIR.mkdir(parents=True, exist_ok=True)
    AGENT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
