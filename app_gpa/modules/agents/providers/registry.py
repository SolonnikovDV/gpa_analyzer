from __future__ import annotations

from typing import List

from ..governance.loader import load_manifest
from .base import AgentProvider, ProviderInfo
from .deepseek import DeepSeekProvider
from .gigachat_provider import GigaChatProvider
from .groq_provider import GroqProvider
from .openrouter_provider import OpenRouterProvider

_PROVIDERS = {
    "gigachat": GigaChatProvider(),
    "deepseek": DeepSeekProvider(),
    "groq": GroqProvider(),
    "openrouter": OpenRouterProvider(),
}


def get_provider(provider_id: str) -> AgentProvider:
    pid = (provider_id or "gigachat").strip().lower()
    if pid not in _PROVIDERS:
        raise ValueError(f"Unknown agent provider: {provider_id}")
    return _PROVIDERS[pid]


def list_providers() -> List[ProviderInfo]:
    manifest = load_manifest()
    cfg = manifest.get("providers") or {}
    out: List[ProviderInfo] = []
    for pid, provider in _PROVIDERS.items():
        meta = cfg.get(pid) or {}
        info = provider.info()
        if meta.get("label"):
            info.label = str(meta["label"])
        if meta.get("default_chat_model"):
            info.default_chat_model = str(meta["default_chat_model"])
        out.append(info)
    return out
