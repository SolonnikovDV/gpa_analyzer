"""Политика мультиагента: лимиты, guard от циклов, конфиг из manifest."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .loader import load_manifest


@dataclass
class MultiAgentSession:
    step_id: str
    stack: str
    provider: str
    started_ms: float = field(default_factory=lambda: time.time() * 1000)
    round_index: int = 0
    messages: List[Dict[str, str]] = field(default_factory=list)
    consensus: Optional[str] = None
    stale: bool = False


def multi_agent_config() -> Dict[str, Any]:
    return dict(load_manifest().get("multi_agent") or {})


def is_multi_agent_enabled(override: Optional[bool] = None) -> bool:
    if override is not None:
        return bool(override)
    import os

    env_flag = os.environ.get("GPA_MULTI_AGENT_ENABLED", "").strip().lower()
    if env_flag in ("1", "true", "yes", "on"):
        return True
    if env_flag in ("0", "false", "no", "off"):
        return False
    return bool(multi_agent_config().get("enabled"))


def should_continue_debate(
    session: MultiAgentSession,
    *,
    multi_agent_override: Optional[bool] = None,
) -> bool:
    if not is_multi_agent_enabled(multi_agent_override):
        return False
    cfg = multi_agent_config()
    max_rounds = int(cfg.get("max_debate_rounds") or 3)
    if session.round_index >= max_rounds:
        return False
    guard_ms = int(cfg.get("cycle_guard_ms") or 120_000)
    elapsed = time.time() * 1000 - session.started_ms
    if elapsed > guard_ms:
        session.stale = True
        return False
    return session.consensus is None


def next_debate_mode(round_index: int) -> str:
    modes = list(multi_agent_config().get("debate_modes") or ["review", "challenge", "synthesize"])
    if not modes:
        return "review"
    return modes[min(round_index, len(modes) - 1)]


def arbiter_role_id() -> str:
    return str(multi_agent_config().get("arbiter_role") or "arbiter")
