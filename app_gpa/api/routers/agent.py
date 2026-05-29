"""FastAPI routers — agent domain.

Canonical API surface for all /api/agent/* endpoints.
Flask blueprint (web/routes/agent.py) is kept for legacy HTML-adjacent routes
only; all JSON API endpoints are served from here.
"""
from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.contracts import error_payload, ok_payload

router = APIRouter(prefix="/agent", tags=["agent"])

# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------


class FlowPlanRequest(BaseModel):
    mode: str = Field(..., description="single | multi")
    stack: str = "greenplum"
    provider: Optional[str] = None
    selected_provider_ids: Optional[List[str]] = None


class ProfileValidateRequest(BaseModel):
    provider: str
    credentials: Optional[str] = None
    scope: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    verify_ssl: Optional[bool] = True
    use_env_credentials: bool = False
    chat_model: Optional[str] = None
    embedding_model: Optional[str] = None
    profile_name: Optional[str] = None


class TokenUsageRequest(BaseModel):
    provider: Optional[str] = None
    credentials: Optional[str] = None
    scope: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None


class GenerateSQLRequest(BaseModel):
    description: str = Field(..., description="Текстовое описание задачи или функции")
    provider: Optional[str] = Field("gigachat", description="Провайдер LLM")
    stack: str = Field("greenplum", description="Стек: greenplum | spark | pyspark")
    credentials: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    scope: Optional[str] = None
    use_env_credentials: bool = False
    chat_model: Optional[str] = None
    with_review: bool = False
    code_revision_pass: bool = True
    multi_agent: Optional[bool] = None


class GigachatProfileItem(BaseModel):
    name: str
    clientId: str = ""
    scope: str = "GIGACHAT_API_PERS"
    tokenFromEnv: Optional[bool] = None
    sourceProfile: Optional[str] = None
    chatModel: Optional[str] = None
    embeddingModel: Optional[str] = None


class SimpleProfileUpsertRequest(BaseModel):
    name: str
    chat_model: str = ""
    api_key_hint: str = ""


class TokensCountRequest(BaseModel):
    input: Optional[Any] = None
    inputs: Optional[Any] = None
    model: Optional[str] = None
    credentials: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    scope: Optional[str] = None


class ProbeModelsRequest(BaseModel):
    provider: Optional[str] = "gigachat"
    credentials: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    scope: Optional[str] = None
    verify_ssl: Optional[bool] = None


# ---------------------------------------------------------------------------
# Provider metadata helpers (used by /providers)
# ---------------------------------------------------------------------------

_PROVIDER_ENV_KEYS: Dict[str, str] = {
    "gigachat": "GIGACHAT_TOKEN",
    "deepseek": "DEEPSEEK_TOKEN",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

_PROVIDER_KEY_PLACEHOLDER: Dict[str, str] = {
    "gigachat": "Base64-токен из личного кабинета GigaChat",
    "deepseek": "sk-… (ключ DeepSeek)",
    "groq": "gsk_… (ключ Groq)",
    "openrouter": "sk-or-… (ключ OpenRouter)",
}

_PROVIDER_DOCS_URL: Dict[str, str] = {
    "groq": "https://console.groq.com",
    "openrouter": "https://openrouter.ai/keys",
    "deepseek": "https://platform.deepseek.com",
}


def _resolve_simple_provider(provider_id: str):
    """Return ProviderInfo for a simple (non-gigachat) provider, or None."""
    try:
        from modules.agents.providers.registry import get_provider
        info = get_provider(provider_id).info()
        return info if info.id != "gigachat" else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Flow plan
# ---------------------------------------------------------------------------


@router.get("/flow/plan")
def get_flow_plan(
    mode: str = Query(...),
    stack: str = Query("greenplum"),
    provider: Optional[str] = Query(None),
    selected_provider_ids: Optional[str] = Query(None, description="comma-separated provider ids"),
) -> Dict[str, Any]:
    from services.agents.api import get_flow_plan as svc_get_flow_plan
    ids = [x.strip() for x in (selected_provider_ids or "").split(",") if x.strip()] or None
    data = svc_get_flow_plan(mode=mode, stack=stack, provider=provider, selected_provider_ids=ids)
    payload, _ = ok_payload(data=data, **data)
    return payload


@router.post("/flow/plan")
def post_flow_plan(body: FlowPlanRequest) -> Dict[str, Any]:
    from services.agents.api import get_flow_plan as svc_get_flow_plan
    data = svc_get_flow_plan(
        mode=body.mode,
        stack=body.stack,
        provider=body.provider,
        selected_provider_ids=body.selected_provider_ids,
    )
    payload, _ = ok_payload(data=data, **data)
    return payload


@router.get("/flow/profile-schema")
def get_profile_schema(provider: str = Query(...)) -> Dict[str, Any]:
    from services.agents.api import profile_schema
    data = profile_schema(provider)
    payload, _ = ok_payload(data=data, **data)
    return payload


@router.post("/flow/validate-profile")
def post_validate_profile(body: ProfileValidateRequest) -> Dict[str, Any]:
    from services.agents.api import validate_profile
    result = validate_profile(body.model_dump())
    if not result.get("valid"):
        payload, status = error_payload(
            "agent_profile_invalid",
            result.get("error") or "Проверка профиля не пройдена",
            http_status=400,
            valid=False,
            provider=result.get("provider"),
        )
        return JSONResponse(content=payload, status_code=status)
    payload, _ = ok_payload(**result)
    return payload


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


@router.get("/providers")
def get_providers() -> Dict[str, Any]:
    """Rich provider registry — includes UI metadata (env_key, docs_url, etc.)."""
    try:
        from modules.agents.credentials import SUPPORTED_PROVIDERS, credentials_configured
        from modules.agents.providers.registry import list_providers
        items = []
        for info in list_providers():
            pid = info.id
            items.append({
                "id": pid,
                "label": info.label,
                "default_chat_model": info.default_chat_model,
                "default_embedding_model": info.default_embedding_model,
                "supports_embeddings": info.supports_embeddings,
                "available_chat_models": getattr(info, "available_chat_models", []),
                "max_timeout_sec": getattr(info, "max_timeout_sec", 120.0),
                "configured": credentials_configured(pid),
                "env_key": _PROVIDER_ENV_KEYS.get(pid, ""),
                "key_placeholder": _PROVIDER_KEY_PLACEHOLDER.get(pid, "API Key"),
                "docs_url": _PROVIDER_DOCS_URL.get(pid, ""),
                "profiles_url": f"/api/agent/profiles/{pid}" if pid != "gigachat" else "/api/agent/profiles",
                "is_simple": pid != "gigachat",
            })
        payload, _ = ok_payload(data={"providers": items, "supported": list(SUPPORTED_PROVIDERS)})
        return payload
    except Exception as exc:
        payload, status = error_payload("agent_providers_failed", str(exc), http_status=500)
        return JSONResponse(content=payload, status_code=status)


# ---------------------------------------------------------------------------
# Env / token status and validation
# ---------------------------------------------------------------------------


@router.get("/env-token-status")
def get_env_token_status(provider: Optional[str] = Query(None)) -> Dict[str, Any]:
    from services.agents.api import env_token_status
    data = env_token_status(provider)
    payload, _ = ok_payload(**data)
    return payload


@router.post("/validate-env")
def post_validate_env(body: Dict[str, Any]) -> Dict[str, Any]:
    from services.agents.api import validate_env_token
    result = validate_env_token(body)
    if not result.get("valid"):
        payload, status = error_payload(
            "agent_validate_env_failed",
            result.get("error") or "validate failed",
            http_status=400,
            valid=False,
            provider=result.get("provider"),
        )
        return JSONResponse(content=payload, status_code=status)
    payload, _ = ok_payload(**result)
    return payload


@router.post("/validate")
def post_validate(body: ProfileValidateRequest) -> Dict[str, Any]:
    return post_validate_profile(body)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@router.get("/status")
@router.post("/status")
def agent_status() -> Dict[str, Any]:
    """Check agent availability (is GigaChat agent importable + credentials present)."""
    try:
        from modules.agents.gigachat_agent import generate_sql_from_description  # noqa: F401
        agent_available = True
    except ImportError:
        agent_available = False
    from modules.agents.credentials import credentials_configured
    has_creds = credentials_configured("gigachat")
    payload, _ = ok_payload(available=bool(has_creds) and agent_available)
    return payload


# ---------------------------------------------------------------------------
# Token usage
# ---------------------------------------------------------------------------


@router.get("/token_usage")
def get_token_usage(provider: Optional[str] = Query(None)) -> Dict[str, Any]:
    from services.agents.api import token_usage_payload
    data = token_usage_payload(provider=provider, credentials=None, scope=None)
    payload, _ = ok_payload(data=data, **data)
    return payload


@router.post("/token_usage")
def post_token_usage(body: TokenUsageRequest) -> Dict[str, Any]:
    from services.agents.api import parse_credentials_body, token_usage_payload
    creds, scope = parse_credentials_body(body.model_dump())
    data = token_usage_payload(provider=body.provider, credentials=creds, scope=scope)
    payload, _ = ok_payload(data=data, **data)
    return payload


# ---------------------------------------------------------------------------
# Tokens count
# ---------------------------------------------------------------------------


@router.post("/tokens_count")
def post_tokens_count(body: TokensCountRequest) -> Dict[str, Any]:
    raw_input = body.input or body.inputs
    if isinstance(raw_input, str):
        strings = [raw_input]
    elif isinstance(raw_input, list):
        strings = [str(x) for x in raw_input]
    else:
        strings = []

    creds = (body.credentials or "").strip()
    if not creds and body.client_id and body.client_secret:
        creds = base64.b64encode(f"{body.client_id}:{body.client_secret}".encode()).decode()

    try:
        from modules.agents.gigachat_agent import count_input_tokens
        from modules.agents.credentials import resolve_credentials
        resolved = creds or resolve_credentials("gigachat") or ""
        result = count_input_tokens(strings, credentials_override=resolved or None, model_override=body.model)
        payload, _ = ok_payload(data=result)
        return payload
    except Exception as exc:
        payload, _ = ok_payload(
            data={"ok": False, "per_input": [], "total": 0, "model": body.model, "error": str(exc)}
        )
        return payload


# ---------------------------------------------------------------------------
# Probe models
# ---------------------------------------------------------------------------


@router.post("/probe-models")
def post_probe_models(body: ProbeModelsRequest) -> Dict[str, Any]:
    provider = (body.provider or "gigachat").strip().lower()

    if provider != "gigachat":
        try:
            from modules.agents.providers.registry import get_provider
            info = get_provider(provider).info()
            out = {
                "ok": True,
                "provider": provider,
                "chat_models": getattr(info, "available_chat_models", [info.default_chat_model]),
                "embedding_models": [],
            }
            payload, _ = ok_payload(data=out)
            return payload
        except Exception as exc:
            payload, status = error_payload("agent_probe_models_failed", str(exc), http_status=500)
            return JSONResponse(content=payload, status_code=status)

    creds = (body.credentials or "").strip()
    if not creds and body.client_id and body.client_secret:
        creds = base64.b64encode(f"{body.client_id}:{body.client_secret}".encode()).decode()
    if not creds:
        from modules.agents.credentials import resolve_credentials
        creds = resolve_credentials("gigachat") or ""
    if not creds:
        payload, status = error_payload(
            "agent_credentials_required",
            "Ключ не передан. Введите токен в модальном окне или задайте .key / GIGACHAT_CREDENTIALS.",
            http_status=400,
        )
        return JSONResponse(content=payload, status_code=status)

    try:
        from modules.agents.gigachat_agent import probe_models_availability
        from modules.agents.credentials import resolve_credentials
        import os
        scope = (body.scope or os.environ.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"))
        out = probe_models_availability(creds, scope_override=scope, verify_ssl_override=body.verify_ssl)
        payload, _ = ok_payload(data=out)
        return payload
    except Exception as exc:
        payload, status = error_payload("agent_probe_models_failed", str(exc), http_status=500)
        return JSONResponse(content=payload, status_code=status)


# ---------------------------------------------------------------------------
# Credentials (stateless acknowledgement endpoint)
# ---------------------------------------------------------------------------


@router.post("/credentials")
def post_credentials() -> Dict[str, Any]:
    """Credentials are NOT stored server-side; passed per-request."""
    payload, _ = ok_payload()
    return payload


# ---------------------------------------------------------------------------
# GigaChat profiles (agent_profiles.json)
# ---------------------------------------------------------------------------


@router.get("/profiles")
def get_gigachat_profiles() -> Dict[str, Any]:
    from web.context import _load_agent_profiles
    profiles = _load_agent_profiles()
    payload, _ = ok_payload(data=profiles, items=profiles)
    return payload


@router.post("/profiles")
def post_gigachat_profiles(body: List[GigachatProfileItem]) -> Dict[str, Any]:
    from web.context import _load_agent_profiles, _save_agent_profiles
    existing = _load_agent_profiles()
    existing_by_name = {p.get("name"): p for p in existing if isinstance(p, dict) and p.get("name")}
    profiles = []
    for p in body:
        name = p.name.strip()
        if not name:
            continue
        item: Dict[str, Any] = {
            "name": name,
            "clientId": p.clientId.strip(),
            "scope": p.scope.strip() or "GIGACHAT_API_PERS",
        }
        if p.tokenFromEnv:
            item["tokenFromEnv"] = True
        if p.sourceProfile:
            item["sourceProfile"] = p.sourceProfile.strip()
        elif name in existing_by_name and existing_by_name[name].get("tokenFromEnv"):
            item["tokenFromEnv"] = True
        if name in existing_by_name and existing_by_name[name].get("sourceProfile"):
            item["sourceProfile"] = existing_by_name[name]["sourceProfile"]
        for model_key, val in [("chatModel", p.chatModel), ("embeddingModel", p.embeddingModel)]:
            if val:
                item[model_key] = val.strip()
            elif name in existing_by_name and existing_by_name[name].get(model_key):
                item[model_key] = existing_by_name[name][model_key]
        profiles.append(item)
    _save_agent_profiles(profiles)
    payload, _ = ok_payload()
    return payload


# ---------------------------------------------------------------------------
# Simple provider profiles (deepseek, groq, openrouter, …)
# ---------------------------------------------------------------------------


@router.get("/profiles/{provider_id}")
def get_simple_profiles(provider_id: str) -> Dict[str, Any]:
    from web.context import _load_simple_profiles
    info = _resolve_simple_provider(provider_id)
    if info is None:
        payload, status = error_payload(
            "unknown_provider",
            f"Провайдер '{provider_id}' не найден или не поддерживается",
            http_status=404,
        )
        return JSONResponse(content=payload, status_code=status)
    profiles = _load_simple_profiles(provider_id)
    payload, _ = ok_payload(data=profiles, items=profiles)
    return payload


@router.post("/profiles/{provider_id}")
def post_simple_profile(provider_id: str, body: SimpleProfileUpsertRequest) -> Dict[str, Any]:
    from web.context import _simple_profile_upsert
    info = _resolve_simple_provider(provider_id)
    if info is None:
        payload, status = error_payload(
            "unknown_provider",
            f"Провайдер '{provider_id}' не найден или не поддерживается",
            http_status=404,
        )
        return JSONResponse(content=payload, status_code=status)
    name = body.name.strip()
    if not name:
        payload, status = error_payload("profile_name_required", "Укажите имя профиля", http_status=400)
        return JSONResponse(content=payload, status_code=status)
    chat_model = body.chat_model.strip()
    allowed = getattr(info, "available_chat_models", [])
    if allowed and chat_model not in allowed:
        chat_model = info.default_chat_model
    profile = _simple_profile_upsert(provider_id, name, chat_model, api_key_hint=body.api_key_hint.strip())
    payload, _ = ok_payload(data=profile)
    return payload


@router.delete("/profiles/{provider_id}/{name}")
def delete_simple_profile(provider_id: str, name: str) -> Dict[str, Any]:
    from web.context import _simple_profile_delete
    info = _resolve_simple_provider(provider_id)
    if info is None:
        payload, status = error_payload(
            "unknown_provider",
            f"Провайдер '{provider_id}' не найден или не поддерживается",
            http_status=404,
        )
        return JSONResponse(content=payload, status_code=status)
    deleted = _simple_profile_delete(provider_id, name)
    if not deleted:
        payload, status = error_payload("profile_not_found", f"Профиль '{name}' не найден", http_status=404)
        return JSONResponse(content=payload, status_code=status)
    payload, _ = ok_payload(deleted=True)
    return payload


# ---------------------------------------------------------------------------
# Model options
# ---------------------------------------------------------------------------


@router.get("/model-options")
def get_model_options(provider: str = Query("gigachat")) -> Dict[str, Any]:
    from modules.agents.providers.registry import get_provider
    pid = provider.strip().lower()
    info = get_provider(pid).info()
    chat = getattr(info, "available_chat_models", None) or [info.default_chat_model]
    emb = [info.default_embedding_model] if info.default_embedding_model else []
    try:
        from modules.agents.gigachat_agent import CHAT_MODEL_PRIORITY, EMBEDDING_MODEL_PRIORITY
        if pid == "gigachat":
            chat = list(CHAT_MODEL_PRIORITY)
            emb = list(EMBEDDING_MODEL_PRIORITY)
    except Exception:
        pass
    data = {"provider": pid, "chat": chat, "embedding": emb}
    payload, _ = ok_payload(data=data, **data)
    return payload


# ---------------------------------------------------------------------------
# Governance
# ---------------------------------------------------------------------------


@router.get("/governance")
def get_governance(stack: str = Query("greenplum")) -> Dict[str, Any]:
    from modules.agents.governance.loader import governance_public_summary
    data = governance_public_summary(stack)
    payload, _ = ok_payload(data=data, **data)
    return payload


# ---------------------------------------------------------------------------
# Generate SQL
# ---------------------------------------------------------------------------


@router.post("/generate")
def post_generate_sql(body: GenerateSQLRequest) -> Dict[str, Any]:
    """Generate SQL/function from natural-language description (canonical FastAPI endpoint)."""
    creds = (body.credentials or "").strip()
    if not creds and body.client_id and body.client_secret:
        creds = base64.b64encode(f"{body.client_id}:{body.client_secret}".encode()).decode()

    if not creds and not body.use_env_credentials:
        payload, status = error_payload(
            "agent_credentials_required",
            "Ключ не передан. Введите ключ в модальном окне «Ввести ключ» и нажмите «Применить».",
            http_status=503,
        )
        return JSONResponse(content=payload, status_code=status)

    if not creds and body.use_env_credentials:
        from modules.agents.credentials import resolve_credentials, normalize_provider
        creds = resolve_credentials(normalize_provider(body.provider)) or ""

    if not creds:
        from modules.agents.credentials import normalize_provider
        pid = normalize_provider(body.provider)
        key_hint = _PROVIDER_ENV_KEYS.get(pid, "GIGACHAT_CREDENTIALS")
        payload, status = error_payload(
            "agent_credentials_not_found",
            f"Ключ не найден в .key ({key_hint}). Введите ключ вручную в модальном окне.",
            http_status=503,
        )
        return JSONResponse(content=payload, status_code=status)

    try:
        from modules.agents.track import generate_sql as track_generate_sql
        gen = track_generate_sql(
            body.description,
            provider=body.provider,
            stack=body.stack,
            credentials_override=creds or None,
            model_override=body.chat_model,
            scope_override=(body.scope or "").strip() or None,
            with_review=body.with_review,
            code_revision_pass=body.code_revision_pass,
            multi_agent=body.multi_agent,
        )
        payload, _ = ok_payload(data=gen, **gen)
        return payload
    except Exception as exc:
        err_str = str(exc)
        err_lower = err_str.lower()
        if "429" in err_str or "Too Many Requests" in err_str:
            payload, status = error_payload("agent_rate_limited", "Превышен лимит запросов (429).", http_status=429)
            return JSONResponse(content=payload, status_code=status)
        if "timed out" in err_lower or "readtimeout" in err_lower.replace(" ", ""):
            payload, status = error_payload(
                "agent_generate_timeout",
                "Таймаут ответа LLM. Задайте GIGACHAT_HTTP_TIMEOUT_SEC в .env.",
                http_status=504,
            )
            return JSONResponse(content=payload, status_code=status)
        payload, status = error_payload("agent_generate_failed", err_str, http_status=500)
        return JSONResponse(content=payload, status_code=status)
