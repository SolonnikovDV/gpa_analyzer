"""Embedding / semantic-cache policy per LLM provider."""
from __future__ import annotations

from .credentials import normalize_provider


def supports_semantic_cache(provider: str | None = None) -> bool:
    """sqlite-vec semantic cache — только GigaChat embeddings (v1)."""
    return normalize_provider(provider) == "gigachat"


def cache_mode_label(provider: str | None = None) -> str:
    if supports_semantic_cache(provider):
        return "exact+semantic"
    return "exact-only"
