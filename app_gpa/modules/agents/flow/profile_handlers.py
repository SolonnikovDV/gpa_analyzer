"""Profile step handlers — один интерфейс, провайдеры как plug-in."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol

from ..credentials import credentials_configured, normalize_provider, resolve_credentials
from ..orchestrator import AgentOrchestrator
from .contracts import ProfilePayload, ProfileValidateResult


class ProfileHandler(Protocol):
    provider_id: str

    def field_schema(self) -> Dict[str, Any]: ...

    def validate(self, payload: ProfilePayload) -> ProfileValidateResult: ...

    def env_token_available(self) -> bool: ...


class _BaseProfileHandler:
    provider_id: str

    def env_token_available(self) -> bool:
        return credentials_configured(self.provider_id)

    def _resolve_creds(self, payload: ProfilePayload) -> Optional[str]:
        if payload.use_env_credentials:
            return resolve_credentials(self.provider_id)
        override = payload.credentials
        if not override and payload.client_id and payload.client_secret:
            import base64

            override = base64.b64encode(f"{payload.client_id}:{payload.client_secret}".encode()).decode()
        return resolve_credentials(self.provider_id, override)

    def validate(self, payload: ProfilePayload) -> ProfileValidateResult:
        creds = self._resolve_creds(payload)
        if not creds:
            return ProfileValidateResult(
                ok=False,
                provider_id=self.provider_id,
                error="Ключ не задан (.key, env или форма)",
                from_env=payload.use_env_credentials,
            )
        try:
            AgentOrchestrator(
                provider=self.provider_id,
                credentials_override=creds,
                model_override=payload.chat_model,
                scope_override=payload.scope,
            ).validate()
            return ProfileValidateResult(
                ok=True,
                provider_id=self.provider_id,
                from_env=payload.use_env_credentials,
            )
        except Exception as e:
            return ProfileValidateResult(
                ok=False,
                provider_id=self.provider_id,
                error=str(e).strip() or type(e).__name__,
                from_env=payload.use_env_credentials,
            )


class GigaChatProfileHandler(_BaseProfileHandler):
    provider_id = "gigachat"

    def field_schema(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "fields": [
                {"id": "profile_name", "type": "text", "label": "Имя профиля"},
                {"id": "credentials", "type": "password", "label": "Token"},
                {"id": "client_id", "type": "text", "label": "Client ID"},
                {"id": "scope", "type": "select", "label": "Scope", "options": [
                    "GIGACHAT_API_PERS", "GIGACHAT_API_B2B", "GIGACHAT_API_CORP",
                ]},
                {"id": "chat_model", "type": "select", "label": "Chat-модель"},
                {"id": "embedding_model", "type": "select", "label": "Embeddings"},
                {"id": "verify_ssl", "type": "checkbox", "label": "Проверять SSL", "default": True},
            ],
            "supports_embeddings": True,
            "supports_env_token": True,
        }

    def validate(self, payload: ProfilePayload) -> ProfileValidateResult:
        creds = self._resolve_creds(payload)
        if not creds:
            return ProfileValidateResult(
                ok=False,
                provider_id=self.provider_id,
                error="Ключ не задан (.key, env или форма)",
                from_env=payload.use_env_credentials,
            )
        try:
            from ..gigachat_agent import validate_credentials

            validate_credentials(
                credentials_override=creds,
                scope_override=payload.scope,
                verify_ssl_override=payload.verify_ssl,
            )
            return ProfileValidateResult(ok=True, provider_id=self.provider_id, from_env=payload.use_env_credentials)
        except Exception as e:
            return ProfileValidateResult(
                ok=False,
                provider_id=self.provider_id,
                error=str(e).strip() or type(e).__name__,
                from_env=payload.use_env_credentials,
            )


_HANDLERS: Dict[str, ProfileHandler] = {
    "gigachat": GigaChatProfileHandler(),
}


def get_profile_handler(provider_id: Optional[str]) -> ProfileHandler:
    pid = normalize_provider(provider_id)
    handler = _HANDLERS.get(pid)
    if handler is None:
        raise ValueError(f"Unknown provider for profile flow: {provider_id}")
    return handler


def list_profile_handlers() -> List[ProfileHandler]:
    return list(_HANDLERS.values())
