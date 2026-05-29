"""OpenRouter HTTP client — OpenAI-compatible SDK wrapper.

Free models (`:free` suffix — no credit card, no balance needed):
  deepseek/deepseek-r1-0528:free           — full DeepSeek R1, best reasoning
  deepseek/deepseek-r1-distill-llama-70b:free — distilled R1
  meta-llama/llama-3.3-70b-instruct:free   — general-purpose
  mistralai/mistral-small-3.2-24b-instruct:free — EU, solid
  nvidia/nemotron-nano-9b-v2:free          — fast reasoning
  openrouter/free                          — auto-router (picks available free model)

Rate limits (free tier): 20 RPM, 200 req/day
Docs: https://openrouter.ai/docs/quick-start
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

FREE_CHAT_MODELS: List[str] = [
    "deepseek/deepseek-r1-0528:free",
    "deepseek/deepseek-r1-distill-llama-70b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "mistralai/mistral-small-3.2-24b-instruct:free",
    "nvidia/nemotron-nano-9b-v2:free",
]
DEFAULT_CHAT_MODEL: str = "deepseek/deepseek-r1-0528:free"

_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_TIMEOUT = 120.0
_APP_TITLE = "GPA Analyzer"
_APP_SITE = "http://localhost:8003"


def _resolve_timeout() -> float:
    raw = os.environ.get("OPENROUTER_HTTP_TIMEOUT_SEC", "").strip()
    if raw:
        try:
            return max(30.0, float(raw))
        except ValueError:
            pass
    return _DEFAULT_TIMEOUT


class OpenRouterClient:
    """OpenAI SDK client scoped to one OpenRouter request."""

    def __init__(self, api_key: str, model: Optional[str] = None) -> None:
        self.api_key = api_key
        self.model = (model or DEFAULT_CHAT_MODEL).strip()
        self.timeout = _resolve_timeout()

    def _build_client(self) -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Установите openai: pip install openai") from exc
        return OpenAI(
            api_key=self.api_key,
            base_url=_BASE_URL,
            timeout=self.timeout,
            default_headers={
                "HTTP-Referer": os.environ.get("OPENROUTER_SITE_URL", _APP_SITE),
                "X-Title": os.environ.get("OPENROUTER_APP_TITLE", _APP_TITLE),
            },
        )

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send chat completion via OpenRouter API.

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
        return RuntimeError("OpenRouter: неверный API Key (401). Проверьте OPENROUTER_API_KEY в .key или .env.")
    if "RateLimitError" in name or "429" in msg:
        return RuntimeError("OpenRouter: превышен лимит запросов (429). Free tier: 20 RPM, 200 req/day. Повторите позже.")
    if "APIConnectionError" in name or "Connection" in name:
        return RuntimeError(f"OpenRouter: ошибка соединения с openrouter.ai. {msg}")
    if "APITimeoutError" in name or "timeout" in msg.lower():
        return RuntimeError("OpenRouter: таймаут ответа API. Повторите запрос.")
    if "BadRequestError" in name or "400" in msg:
        return RuntimeError(f"OpenRouter: неверный запрос (400). {msg}")
    if "402" in msg or "Insufficient" in msg:
        return RuntimeError("OpenRouter: недостаточно средств (402). Пополните баланс или используйте :free модели.")
    return RuntimeError(f"OpenRouter API error ({name}): {msg}")


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
