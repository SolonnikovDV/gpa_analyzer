"""DeepSeek model executor.

Public surface:
  DeepSeekClient  — HTTP client (OpenAI SDK wrapper)
  DeepSeekActions — stateless facade: validate(), chat()
  FREE_CHAT_MODELS, DEFAULT_CHAT_MODEL
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .actions import chat, validate
from .client import DEFAULT_CHAT_MODEL, FREE_CHAT_MODELS, DeepSeekClient


class DeepSeekActions:
    """Stateless facade matching the GigaChat actions pattern."""

    def validate(self, api_key: str, *, model: Optional[str] = None) -> None:
        validate(api_key, model=model)

    def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        api_key: str,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        return chat(
            messages,
            api_key=api_key,
            model=model,
            max_tokens=max_tokens,
        )


__all__ = [
    "DeepSeekClient",
    "DeepSeekActions",
    "FREE_CHAT_MODELS",
    "DEFAULT_CHAT_MODEL",
    "validate",
    "chat",
]
