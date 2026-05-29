from __future__ import annotations

import os
from typing import Any, List, Optional

from .base import AgentProvider, ChatMessage, ChatResult, ProviderInfo


class GigaChatProvider:
    id = "gigachat"

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.id,
            label="GigaChat",
            default_chat_model=os.environ.get("GIGACHAT_MODEL") or "GigaChat-2",
            supports_embeddings=True,
            default_embedding_model=os.environ.get("GIGACHAT_EMBEDDING_MODEL") or "Embeddings-2",
            available_chat_models=[],  # populated dynamically via probe-models API
            max_timeout_sec=120.0,
        )

    def validate(self, credentials: str, **kwargs: Any) -> None:
        from ..gigachat_agent import validate_credentials

        validate_credentials(
            credentials_override=credentials,
            scope_override=kwargs.get("scope"),
            verify_ssl_override=kwargs.get("verify_ssl"),
        )

    def chat(
        self,
        messages: List[ChatMessage],
        *,
        credentials: str,
        model: Optional[str] = None,
        timeout_sec: Optional[float] = None,
        **kwargs: Any,
    ) -> ChatResult:
        from ..gigachat_agent import _add_usage, _resolved_chat_model

        prompt = _messages_to_prompt(messages)

        def _fn(giga):
            response = giga.chat(prompt)
            _add_usage(getattr(response, "usage", None), provider="gigachat")
            text = response.choices[0].message.content if response.choices else ""
            return text, response

        text, raw = _call_giga(_fn, credentials, model, kwargs.get("scope"))
        resolved = _resolved_chat_model(model)
        usage = _usage_dict(raw)
        return ChatResult(text=text or "", provider=self.id, model=resolved, usage=usage, raw=raw)


def _call_giga(fn, credentials: str, model: Optional[str], scope: Optional[str]):
    from ..gigachat_agent import _call_gigachat_chat

    return _call_gigachat_chat(
        fn,
        credentials_override=credentials,
        model_override=model,
        scope_override=scope,
    )


def _messages_to_prompt(messages: List[ChatMessage]) -> str:
    parts: List[str] = []
    for m in messages:
        role = m.role.upper()
        parts.append(f"[{role}]\n{m.content}")
    return "\n\n".join(parts)


def _usage_dict(raw: Any) -> dict:
    usage = getattr(raw, "usage", None)
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return {k: int(v or 0) for k, v in usage.items() if isinstance(v, (int, float))}
    return {
        "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
    }
