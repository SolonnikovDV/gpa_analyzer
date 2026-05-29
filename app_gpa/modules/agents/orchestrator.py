"""Agent orchestrator: governance + provider + optional multi-agent."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

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
    ) -> None:
        self.provider_id = normalize_provider(provider)
        self.stack = (stack or "greenplum").strip().lower()
        self.credentials_override = credentials_override
        self.model_override = model_override
        self.scope_override = scope_override
        self.multi_agent = multi_agent

    def credentials(self) -> str:
        creds = resolve_credentials(self.provider_id, self.credentials_override)
        if not creds:
            raise RuntimeError(
                f"Ключ для {self.provider_id} не задан (.key, env или форма)"
            )
        return creds

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
        provider = get_provider(self.provider_id)
        last: Optional[ChatResult] = None
        while should_continue_debate(session, multi_agent_override=self.multi_agent):
            mode = next_debate_mode(session.round_index)
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
                credentials=self.credentials(),
                model=self.model_override,
                scope=self.scope_override,
            )
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
        return last

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
            "multi_agent": is_multi_agent_enabled(self.multi_agent),
        }
