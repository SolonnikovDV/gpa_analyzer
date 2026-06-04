"""Загрузка governance-артефактов из репозитория (manifest, roles, skills, rules)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

_GOVERNANCE_ROOT = Path(__file__).resolve().parent


def governance_root() -> Path:
    return _GOVERNANCE_ROOT


@lru_cache(maxsize=1)
def load_manifest() -> Dict[str, Any]:
    path = _GOVERNANCE_ROOT / "manifest.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def reload_manifest() -> Dict[str, Any]:
    load_manifest.cache_clear()
    return load_manifest()


def load_role_brief(role_id: str) -> str:
    path = _GOVERNANCE_ROOT / "roles" / f"{role_id}.md"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def load_skill_markdown(skill_id: str = "gpa-agent-team") -> str:
    path = _GOVERNANCE_ROOT / "skills" / skill_id / "SKILL.md"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def load_rule_markdown(rule_id: str = "gpa-agent-track") -> str:
    path = _GOVERNANCE_ROOT / "rules" / f"{rule_id}.mdc"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def governance_public_summary(stack: Optional[str] = None) -> Dict[str, Any]:
    """Без секретов — для API и UI."""
    from .registry import roles_for_stack, roles_for_step

    manifest = load_manifest()
    stack_norm = (stack or "greenplum").strip().lower()
    return {
        "version": manifest.get("version"),
        "team_id": manifest.get("team_id"),
        "stack": stack_norm,
        "core_roles": manifest.get("core_roles", []),
        "stack_roles": manifest.get("stack_roles", {}).get(stack_norm, []),
        "track_steps": list((manifest.get("track_steps") or {}).keys()),
        "providers": list((manifest.get("providers") or {}).keys()),
        "multi_agent": manifest.get("multi_agent", {}),
        "embedding_cache": {
            "gigachat": "exact+semantic",
            "deepseek": "exact-only",
        },
        "roles_for_stack": roles_for_stack(stack_norm),
        "example_step_roles": {
            step: roles_for_step(step, stack_norm)
            for step in ("generate_sql", "blocks_and_objects", "synthesize_plan")
        },
    }
