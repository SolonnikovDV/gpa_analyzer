"""Сборка system/team brief для LLM из governance roles."""
from __future__ import annotations

from typing import Optional

from .loader import load_manifest, load_role_brief
from .registry import normalize_stack, roles_for_step


def compose_team_brief(step_id: str, stack: Optional[str] = None) -> str:
    """Компактный блок для prepend к промпту (один chat-вызов, v1)."""
    stack_norm = normalize_stack(stack)
    manifest = load_manifest()
    step_cfg = (manifest.get("track_steps") or {}).get(step_id) or {}
    step_label = step_cfg.get("label") or step_id
    role_ids = roles_for_step(step_id, stack_norm)

    lines = [
        f"[GPA Agent Team · {manifest.get('team_id', 'gpa-agent-team')} · stack={stack_norm} · step={step_id}]",
        f"Шаг трека: {step_label}.",
        "Активные роли (следуй их brief):",
    ]
    for rid in role_ids:
        brief = load_role_brief(rid)
        if not brief:
            lines.append(f"- {rid}")
            continue
        # только заголовок + первые 2 строки brief
        parts = [p.strip() for p in brief.splitlines() if p.strip() and not p.startswith("#")]
        snippet = " ".join(parts[:2]) if parts else rid
        lines.append(f"- {rid}: {snippet}")

    lines.append(
        "Перед ответом: reviewer — полнота; critic — скрытые риски; arbiter — финальное решение при противоречии."
    )
    return "\n".join(lines)


def enrich_prompt(step_id: str, stack: Optional[str], user_prompt: str) -> str:
    """Prepend team brief к user prompt."""
    brief = compose_team_brief(step_id, stack)
    return f"{brief}\n\n---\n\n{user_prompt}"


_DEBATE_MODE_HINTS = {
    "review": "Режим review: проверь полноту, корректность и соответствие brief ролей reviewer и dba.",
    "challenge": "Режим challenge: найди скрытые риски, edge cases и слабые места (роль critic).",
    "synthesize": "Режим synthesize: собери финальный ответ; при согласии всех ролей начни строку с CONSENSUS:.",
}


def compose_debate_instruction(
    mode: str,
    step_id: str,
    stack: Optional[str] = None,
    *,
    round_index: int = 0,
) -> str:
    """System-дополнение для раунда мультиагента."""
    from .multi_agent_policy import arbiter_role_id

    hint = _DEBATE_MODE_HINTS.get(mode) or f"Режим {mode}."
    arbiter = arbiter_role_id()
    return (
        f"[Multi-agent · round {round_index + 1} · mode={mode} · step={step_id} · stack={stack or 'greenplum'}]\n"
        f"{hint}\n"
        f"При неразрешимом споре — роль {arbiter} формулирует финальное решение.\n"
        f"Если все роли согласны — ответ начинай с CONSENSUS: (одна строка), затем итог."
    )
