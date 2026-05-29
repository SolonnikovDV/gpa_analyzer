"""Agent cache baseline and reset use-cases."""
from __future__ import annotations

from typing import Any, Dict


def baseline_exists() -> bool:
    try:
        from modules.agents.agent_cache_db import baseline_exists as _exists

        return _exists()
    except Exception:
        return False


def save_baseline() -> bool:
    from modules.agents.agent_cache_db import save_baseline as _save

    return _save()


def reset_caches(*, vector: bool, cache: bool, state: bool) -> Dict[str, Any]:
    from modules.agents.agent_cache_db import (
        baseline_exists as _baseline_exists,
        reset_agent_cache,
        reset_state_cache,
        reset_vector_cache,
        restore_baseline_config,
    )

    has_baseline = _baseline_exists()
    config_restored = restore_baseline_config()
    result: Dict[str, Any] = {}
    if config_restored:
        result["config"] = "восстановлено"
    if vector:
        result["vector"] = reset_vector_cache()
    if cache:
        n = reset_agent_cache()
        try:
            from modules.agents.gigachat_agent import reset_agent_cache_memory

            reset_agent_cache_memory()
        except Exception:
            pass
        result["cache"] = n
    if state:
        result["state"] = reset_state_cache()
    return {"reset": result, "from_baseline": has_baseline}
