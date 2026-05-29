"""Stateless facade for OpenRouter model operations."""
from __future__ import annotations

from typing import Dict, List, Optional, Any

from .client import DEFAULT_CHAT_MODEL, OpenRouterClient


def validate(api_key: str, *, model: Optional[str] = None) -> None:
    """Verify API key is valid by sending a minimal ping request."""
    client = OpenRouterClient(api_key=api_key, model=model or DEFAULT_CHAT_MODEL)
    result = client.complete([{"role": "user", "content": "ping"}], max_tokens=8)
    if not (result.get("text") or "").strip():
        raise RuntimeError("OpenRouter: пустой ответ при проверке ключа")


def chat(
    messages: List[Dict[str, str]],
    *,
    api_key: str,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Send a chat completion request via OpenRouter."""
    client = OpenRouterClient(api_key=api_key, model=model or DEFAULT_CHAT_MODEL)
    return client.complete(messages, max_tokens=max_tokens)
