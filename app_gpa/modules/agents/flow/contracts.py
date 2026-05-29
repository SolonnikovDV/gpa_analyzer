"""Unified agent setup flow contracts (provider-agnostic)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class FlowMode(str, Enum):
    SINGLE = "single"
    MULTI = "multi"


class FlowStepKind(str, Enum):
    """Единые шаги UI/API — провайдер встраивается в PROFILE через handler."""

    SELECT_SLOTS = "select_slots"
    PROFILE = "profile"
    READY = "ready"


@dataclass(frozen=True)
class AgentSlot:
    """Один LLM-слот в флоу (single = 1 слот, multi = N слотов)."""

    slot_id: str
    provider_id: str
    label: str
    supports_embeddings: bool
    default_chat_model: str
    default_embedding_model: Optional[str] = None
    governance_roles: List[str] = field(default_factory=list)
    configured: bool = False


@dataclass(frozen=True)
class FlowStep:
    kind: FlowStepKind
    title: str
    slot: Optional[AgentSlot] = None
    index: int = 0
    total: int = 1


@dataclass(frozen=True)
class FlowPlan:
    mode: FlowMode
    stack: str
    governance_team_id: str
    governance_version: str
    steps: List[FlowStep]
    slots: List[AgentSlot]
    multi_agent_policy: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProfilePayload:
    provider_id: str
    credentials: Optional[str] = None
    scope: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    verify_ssl: bool = True
    use_env_credentials: bool = False
    chat_model: Optional[str] = None
    embedding_model: Optional[str] = None
    profile_name: Optional[str] = None


@dataclass
class ProfileValidateResult:
    ok: bool
    provider_id: str
    error: Optional[str] = None
    from_env: bool = False
