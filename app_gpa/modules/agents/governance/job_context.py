"""Governance metadata for job/UI (без секретов)."""
from __future__ import annotations

from typing import Any, Dict

from .loader import load_manifest
from .multi_agent_policy import is_multi_agent_enabled


def governance_job_context() -> Dict[str, Any]:
    manifest = load_manifest()
    ma = dict(manifest.get("multi_agent") or {})
    return {
        "governance_version": manifest.get("version") or "1.0.0",
        "governance_team_id": manifest.get("team_id") or "gpa-agent-team",
        "multi_agent_enabled": is_multi_agent_enabled(),
        "multi_agent_ui_configurable": True,
        "multi_agent_max_rounds": ma.get("max_debate_rounds"),
    }
