"""Startup hooks: restore agent baseline, register and wire all modules."""
from __future__ import annotations

import datetime
import json


def restore_agent_baseline() -> None:
    try:
        from modules.agents.agent_cache_db import restore_baseline_config

        restore_baseline_config()
    except Exception:
        pass


def seed_simple_provider_default_profile(provider_id: str) -> None:
    """Seed a default 'разработчик' profile for any simple (API-key) provider.

    Uses the provider registry to get the default chat model dynamically.
    Skips if token is absent or profile already exists.
    """
    try:
        from modules.agents.credentials import resolve_credentials
        from modules.agents.providers.registry import list_providers
        from core.paths import simple_provider_profiles_path, CONFIG_DIR

        token = resolve_credentials(provider_id)
        if not token:
            return

        # list_providers() returns List[ProviderInfo] — search by .id directly
        provider_info = next(
            (info for info in list_providers() if info.id == provider_id),
            None,
        )
        if provider_info is None:
            return

        profiles_path = simple_provider_profiles_path(provider_id)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        profiles: list = []
        if profiles_path.is_file():
            try:
                with open(profiles_path, "r", encoding="utf-8") as f:
                    profiles = json.load(f)
                    if not isinstance(profiles, list):
                        profiles = []
            except Exception:
                profiles = []

        existing_names = {p.get("name") for p in profiles if isinstance(p, dict)}
        if "разработчик" in existing_names:
            return

        hint = token[-4:] if len(token) > 4 else ""
        profile = {
            "name": "разработчик",
            "chat_model": provider_info.default_chat_model,
            "api_key_hint": hint,
            "created_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "from_env": True,
        }
        profiles.insert(0, profile)
        with open(profiles_path, "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def seed_default_profiles_for_simple_providers() -> None:
    """Seed default 'разработчик' profiles for all registered simple (API-key) providers."""
    try:
        from modules.agents.providers.registry import list_providers
    except Exception:
        return

    # list_providers() returns List[ProviderInfo] — iterate directly
    for info in list_providers():
        try:
            if info.id != "gigachat":
                seed_simple_provider_default_profile(info.id)
        except Exception:
            pass


def register_modules() -> None:
    """Register all application modules with AppFactory and call wire()."""
    from core.factory import AppFactory

    if AppFactory._wired:
        return

    from modules.agents import AgentModule
    from modules.analysis import AnalysisModule

    AppFactory.register("agents", AgentModule())
    AppFactory.register("analysis", AnalysisModule())
    AppFactory.wire()


def startup() -> None:
    """Full application startup sequence."""
    restore_agent_baseline()
    register_modules()
    seed_default_profiles_for_simple_providers()
