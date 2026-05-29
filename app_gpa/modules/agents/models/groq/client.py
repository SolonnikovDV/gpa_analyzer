"""Groq HTTP client — OpenAI-compatible SDK wrapper.

Free tier models (no credit card required):
  deepseek-r1-distill-llama-70b  — reasoning/SQL analysis (recommended)
  llama-3.3-70b-versatile        — general-purpose, fast
  llama-3.1-8b-instant           — ultra-fast lightweight tasks
  qwen-qwq-32b                   — chain-of-thought reasoning

Docs: https://console.groq.com/docs/openai
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

FREE_CHAT_MODELS: List[str] = [
    "deepseek-r1-distill-llama-70b",
    "llama-3.3-70b-versatile",
    "qwen-qwq-32b",
    "llama-3.1-8b-instant",
]
DEFAULT_CHAT_MODEL: str = "deepseek-r1-distill-llama-70b"

_BASE_URL = "https://api.groq.com/openai/v1"
_DEFAULT_TIMEOUT = 60.0
_REASONING_MODELS = {"deepseek-r1-distill-llama-70b", "qwen-qwq-32b"}


def _resolve_timeout(model: str) -> float:
    raw = os.environ.get("GROQ_HTTP_TIMEOUT_SEC", "").strip()
    if raw:
        try:
            return max(10.0, float(raw))
        except ValueError:
            pass
    return _DEFAULT_TIMEOUT


class GroqClient:
    """OpenAI SDK client scoped to one Groq request."""

    def __init__(self, api_key: str, model: Optional[str] = None) -> None:
        self.api_key = api_key
        self.model = (model or DEFAULT_CHAT_MODEL).strip()
        self.timeout = _resolve_timeout(self.model)
        self.is_reasoning = self.model in _REASONING_MODELS

    def _build_client(self) -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Установите openai: pip install openai") from exc
        return OpenAI(api_key=self.api_key, base_url=_BASE_URL, timeout=self.timeout)

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send chat completion via Groq API.

        Returns dict with keys: text, reasoning_content, usage, model, raw.
        Raises RuntimeError with human-readable Russian message on errors.
        """
        client = self._build_client()
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise _translate_error(exc) from exc

        choice = response.choices[0] if response.choices else None
        text = (choice.message.content or "") if choice else ""

        reasoning_content: Optional[str] = None
        if choice and hasattr(choice.message, "reasoning_content"):
            reasoning_content = choice.message.reasoning_content or None

        usage = _parse_usage(response.usage)
        return {
            "text": text,
            "reasoning_content": reasoning_content,
            "usage": usage,
            "model": self.model,
            "raw": response,
        }

    @staticmethod
    def is_available() -> bool:
        try:
            from openai import OpenAI  # noqa: F401
            return True
        except ImportError:
            return False


def _translate_error(exc: Exception) -> RuntimeError:
    name = type(exc).__name__
    msg = str(exc)
    if "AuthenticationError" in name or "401" in msg:
        return RuntimeError("Groq: неверный API Key (401). Проверьте GROQ_API_KEY в .key или .env.")
    if "RateLimitError" in name or "429" in msg:
        return RuntimeError("Groq: превышен лимит запросов (429). Free tier: 30 RPM, 6K TPM. Повторите позже.")
    if "APIConnectionError" in name or "Connection" in name:
        return RuntimeError(f"Groq: ошибка соединения с api.groq.com. {msg}")
    if "APITimeoutError" in name or "timeout" in msg.lower():
        return RuntimeError("Groq: таймаут ответа API.")
    if "BadRequestError" in name or "400" in msg:
        return RuntimeError(f"Groq: неверный запрос (400). {msg}")
    if "402" in msg or "Insufficient" in msg:
        return RuntimeError("Groq: недостаточно средств (402). Пополните баланс.")
    return RuntimeError(f"Groq API error ({name}): {msg}")


def _parse_usage(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        pt = int(raw.get("prompt_tokens") or 0)
        ct = int(raw.get("completion_tokens") or 0)
        tt = int(raw.get("total_tokens") or 0)
    else:
        pt = int(getattr(raw, "prompt_tokens", 0) or 0)
        ct = int(getattr(raw, "completion_tokens", 0) or 0)
        tt = int(getattr(raw, "total_tokens", 0) or 0)
    if tt == 0 and (pt or ct):
        tt = pt + ct
    return {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt}
