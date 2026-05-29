"""DeepSeek HTTP client — OpenAI-compatible SDK wrapper.

Free-tier models (deepseek-v4-flash):
  deepseek-chat     — non-thinking mode (default)
  deepseek-reasoner — thinking mode (returns reasoning_content)

Docs:
  https://api-docs.deepseek.com/api/create-chat-completion
  https://api-docs.deepseek.com/guides/thinking_mode
  https://api-docs.deepseek.com/quick_start/rate_limit
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

FREE_CHAT_MODELS: List[str] = ["deepseek-chat", "deepseek-reasoner"]
DEFAULT_CHAT_MODEL: str = "deepseek-chat"

_THINKING_MODEL = "deepseek-reasoner"
_DEFAULT_TIMEOUT = 120.0
_THINKING_TIMEOUT = 600.0


def _resolve_base_url() -> str:
    return (os.environ.get("DEEPSEEK_API_BASE") or "https://api.deepseek.com").rstrip("/")


def _resolve_timeout(model: str) -> float:
    if (model or "").strip().lower() == _THINKING_MODEL:
        return _THINKING_TIMEOUT
    raw = os.environ.get("AGENT_HTTP_TIMEOUT_SEC", "").strip()
    if raw:
        try:
            return max(30.0, float(raw))
        except ValueError:
            pass
    return _DEFAULT_TIMEOUT


def _is_thinking_model(model: str) -> bool:
    return (model or "").strip().lower() == _THINKING_MODEL


class DeepSeekClient:
    """OpenAI SDK client scoped to one DeepSeek request."""

    def __init__(self, api_key: str, model: Optional[str] = None) -> None:
        self.api_key = api_key
        self.model = (model or DEFAULT_CHAT_MODEL).strip()
        self.base_url = _resolve_base_url()
        self.timeout = _resolve_timeout(self.model)
        self.thinking = _is_thinking_model(self.model)

    def _build_client(self) -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Установите openai: pip install openai") from exc
        return OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send a chat completion request.

        Returns a dict with keys:
          text, reasoning_content, usage (dict), model, raw

        Raises RuntimeError with a human-readable Russian message on API errors.
        """
        client = self._build_client()
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or 4096,
        }
        if self.thinking:
            kwargs["reasoning_effort"] = "high"
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise _translate_openai_error(exc) from exc

        text = ""
        reasoning_content: Optional[str] = None
        if response.choices:
            msg = response.choices[0].message
            text = msg.content or ""
            reasoning_content = getattr(msg, "reasoning_content", None) or None

        raw_usage = getattr(response, "usage", None)
        usage = _parse_usage(raw_usage)

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


def _translate_openai_error(exc: Exception) -> RuntimeError:
    """Convert OpenAI SDK errors to human-readable Russian messages."""
    name = type(exc).__name__
    msg = str(exc)
    if "AuthenticationError" in name or "401" in msg:
        return RuntimeError("DeepSeek: неверный API Key (401). Проверьте DEEPSEEK_TOKEN в .key или .env.")
    if "RateLimitError" in name or "429" in msg:
        return RuntimeError("DeepSeek: превышен лимит запросов (429). Повторите позже.")
    if "APIConnectionError" in name or "Connection" in name:
        return RuntimeError(f"DeepSeek: ошибка соединения с api.deepseek.com. {msg}")
    if "APITimeoutError" in name or "timeout" in msg.lower():
        return RuntimeError("DeepSeek: таймаут ответа API. Для thinking mode ожидание до 10 мин.")
    if "BadRequestError" in name or "400" in msg:
        return RuntimeError(f"DeepSeek: неверный запрос (400). {msg}")
    return RuntimeError(f"DeepSeek API error ({name}): {msg}")


def _parse_usage(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        pt = int(raw.get("prompt_tokens") or 0)
        ct = int(raw.get("completion_tokens") or 0)
        tt = int(raw.get("total_tokens") or 0)
        cached = int(raw.get("prompt_cache_hit_tokens") or 0)
    else:
        pt = int(getattr(raw, "prompt_tokens", 0) or 0)
        ct = int(getattr(raw, "completion_tokens", 0) or 0)
        tt = int(getattr(raw, "total_tokens", 0) or 0)
        # prompt_cache_hit_tokens is nested under prompt_tokens_details in OpenAI SDK
        details = getattr(raw, "prompt_tokens_details", None)
        cached = int(getattr(details, "cached_tokens", 0) or 0) if details else 0
    if tt == 0 and (pt or ct):
        tt = pt + ct
    return {
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": tt,
        "cached_tokens": cached,
    }
