"""Реестр ролей команды агента по stack и шагу трека."""
from __future__ import annotations

from typing import List

from .loader import load_manifest


def normalize_stack(stack: str | None) -> str:
    s = (stack or "greenplum").strip().lower()
    if s in ("spark", "pyspark", "greenplum"):
        return s
    return "greenplum"


def roles_for_stack(stack: str | None) -> List[str]:
    manifest = load_manifest()
    core = list(manifest.get("core_roles") or [])
    stack_norm = normalize_stack(stack)
    extra = list((manifest.get("stack_roles") or {}).get(stack_norm, []))
    seen: set[str] = set()
    out: List[str] = []
    for role in core + extra:
        if role not in seen:
            seen.add(role)
            out.append(role)
    return out


def roles_for_step(step_id: str, stack: str | None) -> List[str]:
    manifest = load_manifest()
    step = (manifest.get("track_steps") or {}).get(step_id) or {}
    roles = list(step.get("roles") or [])
    if step.get("include_stack_roles"):
        stack_norm = normalize_stack(stack)
        for r in (manifest.get("stack_roles") or {}).get(stack_norm, []):
            if r not in roles:
                roles.append(r)
    return roles
