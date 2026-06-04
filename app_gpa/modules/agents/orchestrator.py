"""Agent orchestrator: governance + provider + optional multi-agent."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .credentials import normalize_provider, resolve_credentials
from .governance.multi_agent_policy import (
    MultiAgentSession,
    is_multi_agent_enabled,
    next_debate_mode,
    should_continue_debate,
)
from .governance.prompt_composer import compose_team_brief, compose_debate_instruction, enrich_prompt
from .providers.base import ChatMessage, ChatResult
from .providers.registry import get_provider


class AgentOrchestrator:
    def __init__(
        self,
        *,
        provider: Optional[str] = None,
        stack: Optional[str] = "greenplum",
        credentials_override: Optional[str] = None,
        model_override: Optional[str] = None,
        scope_override: Optional[str] = None,
        multi_agent: Optional[bool] = None,
        multi_agent_providers: Optional[list[str]] = None,
        multi_agent_models: Optional[dict[str, str]] = None,
        event_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.provider_id = normalize_provider(provider)
        self.stack = (stack or "greenplum").strip().lower()
        self.credentials_override = credentials_override
        self.model_override = model_override
        self.scope_override = scope_override
        self.multi_agent = multi_agent
        self.multi_agent_providers = [normalize_provider(p) for p in (multi_agent_providers or []) if p]
        self.multi_agent_models = {
            normalize_provider(k): str(v).strip()
            for k, v in (multi_agent_models or {}).items()
            if k and str(v).strip()
        }
        self.event_hook = event_hook

    def credentials(self) -> str:
        creds = resolve_credentials(self.provider_id, self.credentials_override)
        if not creds:
            raise RuntimeError(
                f"Ключ для {self.provider_id} не задан (.key, env или форма)"
            )
        return creds

    def _credentials_for_provider(self, provider_id: str) -> str:
        pid = normalize_provider(provider_id)
        override = self.credentials_override if pid == self.provider_id else None
        creds = resolve_credentials(pid, override)
        if not creds:
            raise RuntimeError(f"Ключ для {pid} не задан (.key, env или форма)")
        return creds

    def _model_for_provider(self, provider_id: str) -> Optional[str]:
        pid = normalize_provider(provider_id)
        return self.multi_agent_models.get(pid) or self.model_override

    def team_brief(self, step_id: str) -> str:
        return compose_team_brief(step_id, self.stack)

    def enrich_prompt(self, step_id: str, user_prompt: str) -> str:
        return enrich_prompt(step_id, self.stack, user_prompt)

    def chat(
        self,
        step_id: str,
        user_prompt: str,
        *,
        system_extra: Optional[str] = None,
    ) -> ChatResult:
        governed = self.enrich_prompt(step_id, user_prompt)
        messages: List[ChatMessage] = []
        system_parts = [self.team_brief(step_id)]
        if system_extra:
            system_parts.append(system_extra)
        messages.append(ChatMessage(role="system", content="\n".join(system_parts)))
        messages.append(ChatMessage(role="user", content=governed))

        if is_multi_agent_enabled(self.multi_agent):
            return self._chat_multi_agent(step_id, messages)

        provider = get_provider(self.provider_id)
        return provider.chat(
            messages,
            credentials=self.credentials(),
            model=self.model_override,
            scope=self.scope_override,
        )

    def _chat_multi_agent(self, step_id: str, messages: List[ChatMessage]) -> ChatResult:
        session = MultiAgentSession(
            step_id=step_id,
            stack=self.stack,
            provider=self.provider_id,
        )
        provider_ids = self.multi_agent_providers or [self.provider_id]
        provider_ids = [normalize_provider(p) for p in provider_ids if p]
        if not provider_ids:
            provider_ids = [self.provider_id]
        last: Optional[ChatResult] = None
        debate_trace: List[Dict[str, Any]] = []
        while should_continue_debate(session, multi_agent_override=self.multi_agent):
            mode = next_debate_mode(session.round_index)
            provider_id = provider_ids[session.round_index % len(provider_ids)]
            provider = get_provider(provider_id)
            round_messages = list(messages)
            round_messages.append(
                ChatMessage(
                    role="system",
                    content=compose_debate_instruction(
                        mode,
                        step_id,
                        self.stack,
                        round_index=session.round_index,
                    ),
                )
            )
            last = provider.chat(
                round_messages,
                credentials=self._credentials_for_provider(provider_id),
                model=self._model_for_provider(provider_id),
                scope=self.scope_override,
            )
            debate_trace.append(
                {
                    "round": session.round_index + 1,
                    "mode": mode,
                    "role_focus": _role_focus_for_mode(mode),
                    "provider": provider_id,
                    "model": last.model,
                    "text": (last.text or "").strip(),
                }
            )
            self._emit_event("round", debate_trace[-1])
            session.round_index += 1
            session.messages.append({"role": "assistant", "content": last.text or ""})
            text_upper = (last.text or "").upper()
            if "CONSENSUS:" in text_upper:
                session.consensus = last.text
                break
        if last is None:
            raise RuntimeError("Multi-agent session produced no response")
        if session.stale:
            last.text = (last.text or "") + "\n\n[arbiter: session stopped by cycle_guard]"
        consensus = (session.consensus or "").strip() or _extract_consensus(last.text or "")
        if consensus:
            self._emit_event("consensus", {"text": consensus})
        raw_meta: Dict[str, Any] = {
            "debate_trace": debate_trace,
            "consensus": consensus or None,
            "stale": bool(session.stale),
            "rounds": int(session.round_index),
            "provider_raw": last.raw,
        }
        return ChatResult(
            text=last.text,
            provider=last.provider,
            model=last.model,
            usage=last.usage,
            raw=raw_meta,
            reasoning_content=last.reasoning_content,
        )

    def validate(self) -> None:
        get_provider(self.provider_id).validate(
            self.credentials(),
            scope=self.scope_override,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_id,
            "stack": self.stack,
            "model": self.model_override,
            "multi_agent_providers": self.multi_agent_providers,
            "multi_agent_models": self.multi_agent_models,
            "multi_agent": is_multi_agent_enabled(self.multi_agent),
        }

    def _emit_event(self, event: str, data: Dict[str, Any]) -> None:
        hook = self.event_hook
        if not hook:
            return
        try:
            hook({"event": event, "data": data})
        except Exception:
            # UI telemetry must never break generation.
            return


def _extract_consensus(text: str) -> str:
    src = (text or "").strip()
    if not src:
        return ""
    lines = [ln.strip() for ln in src.splitlines() if ln.strip()]
    for ln in lines:
        up = ln.upper()
        if up.startswith("CONSENSUS:"):
            return ln.split(":", 1)[1].strip()
    return ""


def _role_focus_for_mode(mode: str) -> str:
    mm = (mode or "").strip().lower()
    if mm == "review":
        return "reviewer,dba"
    if mm == "challenge":
        return "critic"
    if mm == "synthesize":
        return "arbiter"
    return mm or "team"
