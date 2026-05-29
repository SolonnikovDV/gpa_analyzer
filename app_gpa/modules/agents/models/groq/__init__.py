"""Groq inference client — public API.

Free tier:
  - deepseek-r1-distill-llama-70b  (reasoning, SQL analysis)
  - llama-3.3-70b-versatile        (fast general-purpose)
  - llama-3.1-8b-instant           (ultra-fast, lightweight tasks)
  - qwen-qwq-32b                   (chain-of-thought reasoning)

Limits (free): 30 RPM, ~14 400 req/day, 6K TPM per model
Docs: https://console.groq.com/docs/openai
"""
from __future__ import annotations

from typing import Dict, List, Optional, Any

from .client import DEFAULT_CHAT_MODEL, FREE_CHAT_MODELS, GroqClient
from .actions import chat, validate

__all__ = [
    "DEFAULT_CHAT_MODEL",
    "FREE_CHAT_MODELS",
    "GroqClient",
    "chat",
    "validate",
]
