"""Unified track entrypoints: governance + provider selection."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .agent_prompts import get_prompt
from .credentials import normalize_provider
from .gigachat_agent import _strip_markdown_sql_fence
from .governance.multi_agent_policy import is_multi_agent_enabled
from .orchestrator import AgentOrchestrator


def _orchestrator(
    *,
    provider: str,
    stack: str,
    credentials_override: Optional[str],
    model_override: Optional[str],
    scope_override: Optional[str],
    multi_agent: Optional[bool],
) -> AgentOrchestrator:
    return AgentOrchestrator(
        provider=provider,
        stack=stack,
        credentials_override=credentials_override,
        model_override=model_override,
        scope_override=scope_override,
        multi_agent=multi_agent,
    )


def _generate_via_orchestrator(
    description: str,
    *,
    orch: AgentOrchestrator,
    provider_id: str,
    with_review: bool,
    code_revision_pass: bool,
    use_governance: bool,
) -> Dict[str, Any]:
    analysis: Dict[str, Any] = {"intent": "query", "context_sufficient": True, "warning": None}
    warning = None
    if with_review:
        try:
            analyze_prompt = (
                get_prompt("analyze_description", description=description.strip())
                if get_prompt
                else ""
            )
            if analyze_prompt:
                raw_analysis = orch.chat("analyze_description", analyze_prompt).text or ""
                try:
                    analysis = json.loads(raw_analysis.strip().strip("`").split("\n", 1)[-1])
                except Exception:
                    analysis = {"intent": "query", "context_sufficient": True, "warning": None}
                warning = analysis.get("warning")
                if not analysis.get("context_sufficient", True) and not warning:
                    warning = "Контекст может быть неполным — проверьте сгенерированный SQL."
        except Exception:
            pass

    base = (
        get_prompt("generate_sql", description=description.strip())
        if get_prompt
        else description
    )
    result = orch.chat("generate_sql", base)
    sql_or_ddl = _strip_markdown_sql_fence(result.text)
    revision_applied = False
    code_revision_ran = False
    if with_review and code_revision_pass and sql_or_ddl.strip():
        code_revision_ran = True
        try:
            rev_prompt = (
                get_prompt("revise_sql", sql=sql_or_ddl, description=description.strip())
                if get_prompt
                else sql_or_ddl
            )
            revised = _strip_markdown_sql_fence(orch.chat("revise_sql", rev_prompt).text or "")
            if revised.strip() and revised.strip() != sql_or_ddl.strip():
                sql_or_ddl = revised
                revision_applied = True
        except Exception:
            pass

    out: Dict[str, Any] = {
        "sql_or_ddl": sql_or_ddl,
        "provider": provider_id,
        "model": result.model,
        "governance": use_governance,
        "multi_agent": is_multi_agent_enabled(orch.multi_agent),
    }
    if with_review:
        out.update(
            {
                "warning": warning,
                "analysis": analysis,
                "revision_applied": revision_applied,
                "code_revision_ran": code_revision_ran,
            }
        )
    return out


def generate_sql(
    description: str,
    *,
    provider: Optional[str] = None,
    stack: Optional[str] = None,
    credentials_override: Optional[str] = None,
    model_override: Optional[str] = None,
    scope_override: Optional[str] = None,
    with_review: bool = False,
    code_revision_pass: bool = True,
    use_governance: bool = True,
    multi_agent: Optional[bool] = None,
) -> Dict[str, Any]:
    """Generate SQL/DDL with repo governance and selected provider (always via orchestrator)."""
    pid = normalize_provider(provider)
    stack_norm = (stack or "greenplum").strip().lower()
    orch = _orchestrator(
        provider=pid,
        stack=stack_norm,
        credentials_override=credentials_override,
        model_override=model_override,
        scope_override=scope_override,
        multi_agent=multi_agent,
    )
    return _generate_via_orchestrator(
        description,
        orch=orch,
        provider_id=pid,
        with_review=with_review,
        code_revision_pass=code_revision_pass,
        use_governance=use_governance,
    )
