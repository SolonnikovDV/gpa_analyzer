"""Agent module public API.

Usage:
    from modules.agents import AgentModule
    module = AgentModule()
    module.setup()

The module is registered with AppFactory in core/bootstrap.py.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class AgentModule:
    """Plug-in module for LLM agent capabilities.

    Exposes a stable public interface so the rest of the application
    does not import from sub-packages directly.  Internal provider
    implementations live under models/ and providers/.
    """

    name = "agents"

    # ------------------------------------------------------------------
    # ModuleBase implementation
    # ------------------------------------------------------------------

    def setup(self) -> None:
        from core.paths import ensure_runtime_dirs

        ensure_runtime_dirs()

    def health(self) -> Dict[str, Any]:
        from modules.agents.credentials import SUPPORTED_PROVIDERS, resolve_credentials

        status: Dict[str, Any] = {}
        for pid in SUPPORTED_PROVIDERS:
            status[pid] = {"configured": bool(resolve_credentials(pid))}
        return {"ok": True, "providers": status}

    def metadata(self) -> Dict[str, Any]:
        from modules.agents.providers.registry import list_providers

        return {
            "name": self.name,
            "providers": [p.id for p in list_providers()],
        }

    # ------------------------------------------------------------------
    # Public API — used by services/agents/api.py and FastAPI routers
    # ------------------------------------------------------------------

    def get_orchestrator(
        self,
        *,
        provider: Optional[str] = None,
        stack: str = "greenplum",
        credentials_override: Optional[str] = None,
        model_override: Optional[str] = None,
        scope_override: Optional[str] = None,
        multi_agent: Optional[bool] = None,
    ):
        from modules.agents.orchestrator import AgentOrchestrator

        return AgentOrchestrator(
            provider=provider,
            stack=stack,
            credentials_override=credentials_override,
            model_override=model_override,
            scope_override=scope_override,
            multi_agent=multi_agent,
        )

    def generate_sql(
        self,
        *,
        source_text: str,
        provider: Optional[str] = None,
        stack: str = "greenplum",
        credentials_override: Optional[str] = None,
        model_override: Optional[str] = None,
        scope_override: Optional[str] = None,
        multi_agent: Optional[bool] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        from modules.agents.track import generate_sql as _generate

        return _generate(
            source_text=source_text,
            provider=provider,
            stack=stack,
            credentials_override=credentials_override,
            model_override=model_override,
            scope_override=scope_override,
            multi_agent=multi_agent,
            **kwargs,
        )

    def list_providers(self):
        from modules.agents.providers.registry import list_providers

        return list_providers()

    def get_provider(self, provider_id: str):
        from modules.agents.providers.registry import get_provider

        return get_provider(provider_id)

    def token_usage(
        self,
        *,
        provider: Optional[str] = None,
        credentials_override: Optional[str] = None,
        scope_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        from modules.agents.gigachat_agent import get_token_usage

        return get_token_usage(
            credentials_override=credentials_override,
            scope_override=scope_override,
            provider=provider,
        )

    def governance_summary(self, stack: str = "greenplum") -> Dict[str, Any]:
        from modules.agents.governance.loader import governance_public_summary

        return governance_public_summary(stack)
