"""OpenRouter provider adapter (thin layer over models/openrouter/).

Implements AgentProvider protocol; all HTTP logic lives in models/openrouter/.
Free tier: deepseek-r1-0528:free, llama-3.3-70b:free — no credit card, 200 req/day.
"""
from __future__ import annotations

import os
from typing import Any, List, Optional

from .base import ChatMessage, ChatResult, ProviderInfo


class OpenRouterProvider:
    id = "openrouter"

    def info(self) -> ProviderInfo:
        from ..models.openrouter import DEFAULT_CHAT_MODEL, FREE_CHAT_MODELS

        return ProviderInfo(
            id=self.id,
            label="OpenRouter (free · 200 req/day)",
            default_chat_model=os.environ.get("OPENROUTER_MODEL") or DEFAULT_CHAT_MODEL,
            supports_embeddings=False,
            available_chat_models=list(FREE_CHAT_MODELS),
            max_timeout_sec=120.0,
        )

    def validate(self, credentials: str, **kwargs: Any) -> None:
        from ..models.openrouter import validate as _validate

        info = self.info()
        model = (kwargs.get("model") or info.default_chat_model or "").strip()
        if model and model not in (info.available_chat_models or []):
            model = info.default_chat_model
        _validate(credentials, model=model)

    def chat(
        self,
        messages: List[ChatMessage],
        *,
        credentials: str,
        model: Optional[str] = None,
        timeout_sec: Optional[float] = None,
        **kwargs: Any,
    ) -> ChatResult:
        from ..models.openrouter import chat as _chat
        from ..token_usage import record_usage

        oai_messages = [{"role": m.role, "content": m.content} for m in messages]
        resolved_model = (model or self.info().default_chat_model).strip()
        info = self.info()
        if resolved_model and resolved_model not in (info.available_chat_models or []):
            resolved_model = info.default_chat_model

        result = _chat(
            oai_messages,
            api_key=credentials,
            model=resolved_model,
        )

        usage = result.get("usage", {})
        try:
            record_usage(usage, provider=self.id)
            from ..agent_cache_db import add_token_usage
            add_token_usage(
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
                usage.get("total_tokens", 0),
                1,
            )
        except Exception:
            pass

        return ChatResult(
            text=result.get("text", ""),
            provider=self.id,
            model=resolved_model,
            usage=usage,
            raw=result.get("raw"),
            reasoning_content=result.get("reasoning_content"),
        )
