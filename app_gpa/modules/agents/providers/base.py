from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class ChatResult:
    text: str
    provider: str
    model: str
    usage: Dict[str, Any] = field(default_factory=dict)
    raw: Any = None
    reasoning_content: Optional[str] = None


@dataclass
class ProviderInfo:
    id: str
    label: str
    default_chat_model: str
    supports_embeddings: bool = False
    default_embedding_model: Optional[str] = None
    available_chat_models: List[str] = field(default_factory=list)
    max_timeout_sec: float = 120.0


class AgentProvider(Protocol):
    id: str

    def info(self) -> ProviderInfo: ...

    def validate(self, credentials: str, **kwargs: Any) -> None: ...

    def chat(
        self,
        messages: List[ChatMessage],
        *,
        credentials: str,
        model: Optional[str] = None,
        timeout_sec: Optional[float] = None,
        **kwargs: Any,
    ) -> ChatResult: ...
