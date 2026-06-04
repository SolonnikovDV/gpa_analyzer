"""DeepSeek stateless actions — validation and chat."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .client import DEFAULT_CHAT_MODEL, DeepSeekClient


def validate(api_key: str, *, model: Optional[str] = None) -> None:
    """Verify API key with a minimal ping request.

    Raises RuntimeError on auth failure or empty response.
    """
    client = DeepSeekClient(api_key=api_key, model=model or DEFAULT_CHAT_MODEL)
    result = client.complete(
        [{"role": "user", "content": "ping"}],
        max_tokens=8,
    )
    if not (result.get("text") or "").strip():
        raise RuntimeError("DeepSeek: пустой ответ при проверке ключа")


def chat(
    messages: List[Dict[str, str]],
    *,
    api_key: str,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Send a chat completion and return structured result dict."""
    client = DeepSeekClient(api_key=api_key, model=model or DEFAULT_CHAT_MODEL)
    return client.complete(messages, max_tokens=max_tokens)
