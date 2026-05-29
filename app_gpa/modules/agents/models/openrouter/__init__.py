"""OpenRouter inference client — public API.

Free tier (`:free` suffix models, no credit card):
  deepseek/deepseek-r1-0528:free           — full DeepSeek R1 (best reasoning)
  deepseek/deepseek-r1-distill-llama-70b:free — distilled R1
  meta-llama/llama-3.3-70b-instruct:free   — general-purpose
  mistralai/mistral-small-3.2-24b-instruct:free — EU-hosted, solid
  nvidia/nemotron-nano-9b-v2:free          — fast reasoning

Limits (free): 20 RPM, 200 req/day
Docs: https://openrouter.ai/docs
"""
from __future__ import annotations

from .client import DEFAULT_CHAT_MODEL, FREE_CHAT_MODELS, OpenRouterClient
from .actions import chat, validate

__all__ = [
    "DEFAULT_CHAT_MODEL",
    "FREE_CHAT_MODELS",
    "OpenRouterClient",
    "chat",
    "validate",
]
