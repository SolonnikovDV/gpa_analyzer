"""Agent API business logic — application service for HTTP adapters."""
from __future__ import annotations

import asyncio
import base64
from typing import Any, Dict, List, Optional

from modules.agents.credentials import credentials_configured, normalize_provider, resolve_credentials
from modules.agents.flow.contracts import ProfilePayload
from modules.agents.flow.factory import build_flow_plan, flow_plan_to_dict
from modules.agents.flow.profile_handlers import get_profile_handler
from modules.agents.providers.registry import list_providers


def ensure_event_loop() -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())


def resolve_agent_credentials(
    provider: Optional[str] = None,
    override: Optional[str] = None,
    *,
    use_env: bool = False,
) -> Optional[str]:
    if override and str(override).strip():
        return str(override).strip()
    if use_env:
        return resolve_credentials(provider)
    return resolve_credentials(provider, override)


def parse_credentials_body(data: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    creds = (data.get("credentials") or "").strip() or None
    cid = (data.get("client_id") or "").strip()
    csec = (data.get("client_secret") or "").strip()
    if cid and csec:
        creds = base64.b64encode(f"{cid}:{csec}".encode()).decode()
    scope = (data.get("scope") or "").strip() or None
    return creds, scope


def list_providers_payload() -> Dict[str, Any]:
    items = []
    for info in list_providers():
        items.append(
            {
                "id": info.id,
                "label": info.label,
                "default_chat_model": info.default_chat_model,
                "default_embedding_model": info.default_embedding_model,
                "supports_embeddings": info.supports_embeddings,
                "configured": credentials_configured(info.id),
            }
        )
    return {"providers": items}


def get_flow_plan(
    *,
    mode: str,
    stack: str = "greenplum",
    provider: Optional[str] = None,
    selected_provider_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    plan = build_flow_plan(
        mode=mode,
        stack=stack,
        provider=provider,
        selected_provider_ids=selected_provider_ids,
    )
    return flow_plan_to_dict(plan)


def validate_profile(data: Dict[str, Any]) -> Dict[str, Any]:
    provider = normalize_provider(data.get("provider"))
    creds, scope = parse_credentials_body(data)
    payload = ProfilePayload(
        provider_id=provider,
        credentials=creds,
        scope=scope or data.get("scope"),
        client_id=(data.get("client_id") or "").strip() or None,
        client_secret=(data.get("client_secret") or "").strip() or None,
        verify_ssl=data.get("verify_ssl") is not False,
        use_env_credentials=data.get("use_env_credentials") is True,
        chat_model=(data.get("chat_model") or data.get("model") or "").strip() or None,
        embedding_model=(data.get("embedding_model") or "").strip() or None,
        profile_name=(data.get("profile_name") or "").strip() or None,
    )
    result = get_profile_handler(provider).validate(payload)
    return {
        "valid": result.ok,
        "provider": result.provider_id,
        "error": result.error,
        "from_env": result.from_env,
    }


def env_token_status(provider: Optional[str]) -> Dict[str, Any]:
    pid = normalize_provider(provider)
    creds = resolve_credentials(pid)
    return {"hasToken": bool(creds), "provider": pid}


def validate_env_token(data: Dict[str, Any]) -> Dict[str, Any]:
    provider = normalize_provider(data.get("provider"))
    creds = resolve_credentials(provider)
    if not creds:
        key_hint = "DEEPSEEK_TOKEN" if provider == "deepseek" else "GIGACHAT_CREDENTIALS / GIGACHAT_TOKEN"
        return {
            "ok": False,
            "valid": False,
            "provider": provider,
            "error": f"Токен не задан. Добавьте в .key или env: {key_hint}.",
        }
    ensure_event_loop()
    payload = ProfilePayload(provider_id=provider, use_env_credentials=True, scope=data.get("scope"))
    result = get_profile_handler(provider).validate(payload)
    return {
        "ok": result.ok,
        "valid": result.ok,
        "provider": provider,
        "error": result.error,
    }


def token_usage_payload(
    *,
    provider: Optional[str],
    credentials: Optional[str],
    scope: Optional[str],
) -> Dict[str, Any]:
    from modules.agents.gigachat_agent import get_token_usage

    try:
        return get_token_usage(
            credentials_override=credentials,
            scope_override=scope,
            provider=provider,
        )
    except Exception:
        return {
            "used": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "available": None,
            "by_provider": {},
        }


def profile_schema(provider: Optional[str]) -> Dict[str, Any]:
    return get_profile_handler(provider).field_schema()
