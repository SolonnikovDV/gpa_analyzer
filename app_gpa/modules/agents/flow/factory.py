"""Flow factory — единый план setup для single и multi-agent."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..credentials import credentials_configured, normalize_provider
from ..governance.loader import load_manifest
from ..governance.multi_agent_policy import multi_agent_config
from ..governance.registry import roles_for_step
from ..providers.registry import list_providers
from .contracts import AgentSlot, FlowMode, FlowPlan, FlowStep, FlowStepKind


def _provider_slot(provider_id: str, stack: str, *, multi: bool) -> AgentSlot:
    from ..providers.registry import get_provider

    info = get_provider(provider_id).info()
    roles = roles_for_step("generate_sql", stack) if multi else []
    return AgentSlot(
        slot_id=f"llm-{provider_id}",
        provider_id=info.id,
        label=info.label,
        supports_embeddings=info.supports_embeddings,
        default_chat_model=info.default_chat_model,
        default_embedding_model=info.default_embedding_model,
        governance_roles=roles,
        configured=credentials_configured(info.id),
    )


def build_flow_plan(
    *,
    mode: str,
    stack: str = "greenplum",
    provider: Optional[str] = None,
    selected_provider_ids: Optional[List[str]] = None,
) -> FlowPlan:
    """Строит единый FlowPlan. Провайдеры — слоты; шаг PROFILE одинаков для всех."""
    stack_norm = (stack or "greenplum").strip().lower()
    manifest = load_manifest()
    flow_mode = FlowMode.MULTI if (mode or "").strip().lower() == "multi" else FlowMode.SINGLE

    if flow_mode == FlowMode.SINGLE:
        pid = normalize_provider(provider)
        slots = [_provider_slot(pid, stack_norm, multi=False)]
        steps = [
            FlowStep(
                kind=FlowStepKind.PROFILE,
                title=f"Профиль: {slots[0].label}",
                slot=slots[0],
                index=1,
                total=1,
            ),
            FlowStep(kind=FlowStepKind.READY, title="Готово", index=1, total=1),
        ]
    else:
        available = [p.id for p in list_providers()]
        picked = [normalize_provider(x) for x in (selected_provider_ids or []) if x]
        if not picked:
            picked = available[:]
        slots = [_provider_slot(pid, stack_norm, multi=True) for pid in picked if pid in available]
        if not slots:
            slots = [_provider_slot("gigachat", stack_norm, multi=True)]

        steps: List[FlowStep] = [
            FlowStep(
                kind=FlowStepKind.SELECT_SLOTS,
                title="Выбор активных LLM",
                index=1,
                total=len(slots) + 1,
            ),
        ]
        for i, slot in enumerate(slots, start=1):
            steps.append(
                FlowStep(
                    kind=FlowStepKind.PROFILE,
                    title=f"Профиль: {slot.label}",
                    slot=slot,
                    index=i,
                    total=len(slots),
                )
            )
        steps.append(
            FlowStep(
                kind=FlowStepKind.READY,
                title="Multi-agent готов",
                index=len(slots),
                total=len(slots),
            )
        )

    return FlowPlan(
        mode=flow_mode,
        stack=stack_norm,
        governance_team_id=str(manifest.get("team_id") or "gpa-agent-team"),
        governance_version=str(manifest.get("version") or "1.0.0"),
        steps=steps,
        slots=slots,
        multi_agent_policy=dict(multi_agent_config()),
    )


def flow_plan_to_dict(plan: FlowPlan) -> Dict[str, Any]:
    def step_dict(s: FlowStep) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "kind": s.kind.value,
            "title": s.title,
            "index": s.index,
            "total": s.total,
        }
        if s.slot:
            d["slot"] = slot_dict(s.slot)
        return d

    def slot_dict(sl: AgentSlot) -> Dict[str, Any]:
        return {
            "slot_id": sl.slot_id,
            "provider_id": sl.provider_id,
            "label": sl.label,
            "supports_embeddings": sl.supports_embeddings,
            "default_chat_model": sl.default_chat_model,
            "default_embedding_model": sl.default_embedding_model,
            "governance_roles": sl.governance_roles,
            "configured": sl.configured,
            "profile_schema": _profile_schema(sl.provider_id),
        }

    return {
        "mode": plan.mode.value,
        "stack": plan.stack,
        "governance_team_id": plan.governance_team_id,
        "governance_version": plan.governance_version,
        "multi_agent_policy": plan.multi_agent_policy,
        "steps": [step_dict(s) for s in plan.steps],
        "slots": [slot_dict(s) for s in plan.slots],
    }


def _profile_schema(provider_id: str) -> Dict[str, Any]:
    from .profile_handlers import get_profile_handler

    return get_profile_handler(provider_id).field_schema()
