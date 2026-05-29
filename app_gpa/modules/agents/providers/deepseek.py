"""DeepSeek provider adapter (thin layer over models/deepseek/).

Implements AgentProvider protocol; all HTTP logic lives in models/deepseek/.
"""
from __future__ import annotations

import os
from typing import Any, List, Optional

from .base import ChatMessage, ChatResult, ProviderInfo


class DeepSeekProvider:
    id = "deepseek"

    def info(self) -> ProviderInfo:
        from ..models.deepseek import DEFAULT_CHAT_MODEL, FREE_CHAT_MODELS

        return ProviderInfo(
            id=self.id,
            label="DeepSeek",
            default_chat_model=os.environ.get("DEEPSEEK_MODEL") or DEFAULT_CHAT_MODEL,
            supports_embeddings=False,
            available_chat_models=list(FREE_CHAT_MODELS),
            max_timeout_sec=600.0,
        )

    def validate(self, credentials: str, **kwargs: Any) -> None:
        from ..models.deepseek import validate as _validate

        model = kwargs.get("model") or self.info().default_chat_model
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
        from ..models.deepseek import chat as _chat
        from ..token_usage import record_usage

        oai_messages = [{"role": m.role, "content": m.content} for m in messages]
        resolved_model = (model or self.info().default_chat_model).strip()

        result = _chat(oai_messages, api_key=credentials, model=resolved_model)

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
