"""Agent API business logic — application service for HTTP adapters."""
from __future__ import annotations

import asyncio
import base64
import os
from typing import Any, Dict, List, Optional

from modules.agents.credentials import (
    credentials_configured,
    normalize_provider,
    resolve_credentials,
    resolve_credentials_with_source,
)
from modules.agents.flow.contracts import ProfilePayload
from modules.agents.flow.factory import build_flow_plan, flow_plan_to_dict
from modules.agents.flow.profile_handlers import get_profile_handler
from modules.agents.providers.registry import list_providers

_PROVIDER_ENV_HINTS: Dict[str, str] = {
    "gigachat": "GIGACHAT_CREDENTIALS / GIGACHAT_TOKEN",
    "deepseek": "DEEPSEEK_TOKEN / DEEPSEEK_API_KEY",
    "groq": "GROQ_API_KEY / GROQ_TOKEN",
    "openrouter": "OPENROUTER_API_KEY / OPENROUTER_TOKEN",
}


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
    resolved = resolve_credentials_with_source(pid)
    creds = resolved.get("value")
    return {
        "hasToken": bool(creds),
        "provider": pid,
        "source": resolved.get("source") or "none",
        "key": resolved.get("key"),
    }


def validate_env_token(data: Dict[str, Any]) -> Dict[str, Any]:
    provider = normalize_provider(data.get("provider"))
    resolved = resolve_credentials_with_source(provider)
    creds = resolved.get("value")
    if not creds:
        key_hint = _PROVIDER_ENV_HINTS.get(provider, _PROVIDER_ENV_HINTS["gigachat"])
        return {
            "ok": False,
            "valid": False,
            "provider": provider,
            "error": f"Токен не задан. Добавьте в .key или env: {key_hint}.",
            "source": resolved.get("source") or "none",
            "key": resolved.get("key"),
        }
    ensure_event_loop()
    payload = ProfilePayload(
        provider_id=provider,
        use_env_credentials=True,
        scope=data.get("scope"),
        verify_ssl=data.get("verify_ssl") is not False,
        chat_model=(data.get("chat_model") or "").strip() or None,
    )
    result = get_profile_handler(provider).validate(payload)
    return {
        "ok": result.ok,
        "valid": result.ok,
        "provider": provider,
        "error": result.error,
        "verify_ssl_used": payload.verify_ssl,
        "source": resolved.get("source") or "none",
        "key": resolved.get("key"),
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


def network_debug(data: Dict[str, Any]) -> Dict[str, Any]:
    """Network diagnostics for GigaChat transport and auth path."""
    provider = "gigachat"
    verify_ssl = data.get("verify_ssl") is not False
    auth_probe = data.get("auth_probe") is not False
    timeout_sec = 8.0
    scope = (data.get("scope") or os.environ.get("GIGACHAT_SCOPE") or "GIGACHAT_API_PERS").strip()

    resolved = resolve_credentials_with_source(provider)
    creds = resolved.get("value")

    oauth_url = (os.environ.get("GIGACHAT_AUTH_URL") or "https://ngw.devices.sberbank.ru:9443/api/v2/oauth").strip()
    api_models_url = (os.environ.get("GIGACHAT_BASE_URL") or "https://gigachat.devices.sberbank.ru/api/v1").rstrip("/") + "/models"

    env_proxy: Dict[str, str] = {}
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        val = (os.environ.get(key) or "").strip()
        if val:
            env_proxy[key] = val

    report: Dict[str, Any] = {
        "provider": provider,
        "scope": scope,
        "verify_ssl": verify_ssl,
        "has_credentials": bool(creds),
        "credentials_source": resolved.get("source") or "none",
        "credentials_key": resolved.get("key"),
        "transport": {
            "trust_env": True,
            "timeout_sec": timeout_sec,
            "proxy_env_detected": bool(env_proxy),
            "proxy_env_keys": sorted(env_proxy.keys()),
            "ca_bundle_file": (os.environ.get("GIGACHAT_CA_BUNDLE_FILE") or "").strip() or None,
            "oauth_url": oauth_url,
            "api_models_url": api_models_url,
        },
        "probes": {},
    }

    report["probes"]["oauth_endpoint"] = _probe_http_url(
        oauth_url,
        timeout_sec=timeout_sec,
        trust_env=True,
        verify=verify_ssl,
    )
    report["probes"]["api_models_endpoint"] = _probe_http_url(
        api_models_url,
        timeout_sec=timeout_sec,
        trust_env=True,
        verify=verify_ssl,
    )

    if auth_probe and creds:
        try:
            from modules.agents.gigachat_agent import validate_credentials

            validate_credentials(
                credentials_override=creds,
                scope_override=scope,
                verify_ssl_override=verify_ssl,
            )
            report["probes"]["sdk_auth"] = {"ok": True}
        except Exception as exc:
            report["probes"]["sdk_auth"] = {"ok": False, "error": str(exc).strip() or type(exc).__name__}
    else:
        report["probes"]["sdk_auth"] = {
            "ok": False,
            "skipped": True,
            "reason": "no_credentials" if not creds else "disabled_by_request",
        }

    return report


def _probe_http_url(
    url: str,
    *,
    timeout_sec: float,
    trust_env: bool,
    verify: bool,
) -> Dict[str, Any]:
    try:
        import httpx

        with httpx.Client(timeout=timeout_sec, trust_env=trust_env, verify=verify, follow_redirects=False) as client:
            try:
                resp = client.options(url)
                return {
                    "ok": True,
                    "method": "OPTIONS",
                    "status_code": int(resp.status_code),
                }
            except Exception:
                resp = client.get(url)
                return {
                    "ok": True,
                    "method": "GET",
                    "status_code": int(resp.status_code),
                }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc).strip() or type(exc).__name__,
        }
