"""Agent LLM API routes (/api/agent/*)."""
from __future__ import annotations

import base64
from typing import Any, Dict, Optional

from flask import Blueprint, request

from modules.analysis.api_contracts import api_error, api_ok, read_json_object
from modules.analysis.request_validation import RequestValidationError, expect_list_payload, require_non_empty_string
from web.context import (
    _agent_chat_model_from,
    _agent_credentials,
    _agent_embedding_model_from,
    _agent_multi_agent_from,
    _agent_provider_from,
    _agent_scope,
    _agent_stack_from,
    _ensure_event_loop,
    _governance_template_context,
    _load_agent_profiles,
    _resolve_agent_credentials,
    _save_agent_profiles,
)

bp = Blueprint("agent", __name__)


@bp.route("/api/agent/env-token-status", methods=["GET"])
def api_agent_env_token_status():
    """Проверка наличия токена в .key или .env (без раскрытия значения)."""
    provider = _agent_provider_from({"provider": request.args.get("provider")})
    creds = _resolve_agent_credentials(provider, use_env=True)
    return api_ok(hasToken=bool(creds), provider=provider)


@bp.route("/api/agent/validate-env", methods=["POST"])
def api_agent_validate_env():
    """Проверка валидности токена из .key или .env."""
    data = read_json_object()
    provider = _agent_provider_from(data)
    creds = _resolve_agent_credentials(provider, use_env=True)
    if not creds:
        key_hint = "DEEPSEEK_TOKEN" if provider == "deepseek" else "GIGACHAT_CREDENTIALS / GIGACHAT_TOKEN"
        return api_error(
            "agent_credentials_missing",
            f"Токен не задан. Добавьте в .key (корень проекта) или в .env: {key_hint}.",
            http_status=400,
            valid=False,
        )
    _ensure_event_loop()
    try:
        info = _resolve_simple_provider(provider)
        if info is not None:
            from modules.agents.orchestrator import AgentOrchestrator
            AgentOrchestrator(provider=provider, credentials_override=creds).validate()
        else:
            from modules.agents.gigachat_agent import validate_credentials
            scope = (data.get("scope") or "").strip() or _agent_scope()
            validate_credentials(credentials_override=creds, scope_override=scope)
        return api_ok(valid=True, provider=provider)
    except Exception as e:
        return api_error("agent_validate_env_failed", str(e), valid=False, provider=provider)


@bp.route("/api/agent/status", methods=["GET", "POST"])
def api_agent_status():
    """Проверка доступности режима агента."""
    creds = None
    if request.method == "POST":
        data = read_json_object()
        creds = (data.get("credentials") or "").strip()
        cid = (data.get("client_id") or "").strip()
        csec = (data.get("client_secret") or "").strip()
        if cid and csec:
            creds = base64.b64encode(f"{cid}:{csec}".encode()).decode()
    try:
        from modules.agents.gigachat_agent import generate_sql_from_description
        agent_available = generate_sql_from_description is not None
    except ImportError:
        agent_available = False
    return api_ok(available=bool(_agent_credentials(creds)) and agent_available)


@bp.route("/api/agent/token_usage", methods=["GET", "POST"])
def api_agent_token_usage():
    """Использованные токены и остаток по провайдеру."""
    creds = None
    scope = None
    provider = (request.args.get("provider") or "").strip() or None
    if request.method == "POST":
        data = read_json_object()
        creds = (data.get("credentials") or "").strip()
        cid = (data.get("client_id") or "").strip()
        csec = (data.get("client_secret") or "").strip()
        if cid and csec:
            creds = base64.b64encode(f"{cid}:{csec}".encode()).decode()
        scope = (data.get("scope") or "").strip()
        provider = (data.get("provider") or provider or "").strip() or None
    try:
        from modules.agents.gigachat_agent import get_token_usage
        data = get_token_usage(
            credentials_override=_agent_credentials(creds),
            scope_override=_agent_scope(scope),
            provider=provider,
        )
        return api_ok(data=data, **data)
    except Exception:
        fallback = {
            "used": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "available": None,
            "by_provider": {},
        }
        return api_ok(data=fallback, **fallback)


@bp.route("/api/agent/tokens_count", methods=["POST"])
def api_agent_tokens_count():
    """Подсчёт токенов в строках."""
    data = read_json_object()
    raw_input = data.get("input") or data.get("inputs")
    if isinstance(raw_input, str):
        strings = [raw_input]
    elif isinstance(raw_input, list):
        strings = [str(x) for x in raw_input]
    else:
        strings = []
    model = (data.get("model") or "").strip() or None
    creds = (data.get("credentials") or "").strip()
    cid = (data.get("client_id") or "").strip()
    csec = (data.get("client_secret") or "").strip()
    if cid and csec:
        creds = base64.b64encode(f"{cid}:{csec}".encode()).decode()
    scope = (data.get("scope") or "").strip()
    try:
        from modules.agents.gigachat_agent import count_input_tokens
        result = count_input_tokens(
            strings,
            credentials_override=_agent_credentials(creds),
            scope_override=_agent_scope(scope),
            model_override=model,
        )
        return api_ok(data=result)
    except Exception as e:
        return api_ok(
            data={"ok": False, "per_input": [], "total": 0, "model": model, "error": str(e)},
            http_status=200,
        )


@bp.route("/api/agent/validate", methods=["POST"])
def api_agent_validate():
    """Проверка валидности кредов LLM-провайдера."""
    data = read_json_object()
    creds = (data.get("credentials") or "").strip()
    scope = (data.get("scope") or "").strip()
    provider = _agent_provider_from(data)
    verify_ssl = data.get("verify_ssl")
    verify_ssl = True if verify_ssl is None else bool(verify_ssl)
    if not creds:
        return api_error("agent_token_missing", "Не указан Token", http_status=400, valid=False)
    _ensure_event_loop()
    try:
        if provider == "deepseek":
            from modules.agents.orchestrator import AgentOrchestrator
            AgentOrchestrator(provider="deepseek", credentials_override=_agent_credentials(creds)).validate()
            return api_ok(valid=True)
        from modules.agents.gigachat_agent import validate_credentials
        validate_credentials(
            credentials_override=_agent_credentials(creds),
            scope_override=_agent_scope(scope),
            verify_ssl_override=verify_ssl,
        )
        return api_ok(valid=True)
    except Exception as e:
        err = str(e)
        if "401" in err or "Unauthorized" in err or "credentials" in err.lower():
            return api_error("agent_token_invalid", "Токен недействителен или истёк.", http_status=401, valid=False)
        return api_error("agent_validate_failed", err, valid=False)


@bp.route("/api/agent/probe-models", methods=["POST"])
def api_agent_probe_models():
    """Проверка доступности чат- и embedding-моделей."""
    data = read_json_object()
    provider = _agent_provider_from(data)

    if provider == "deepseek":
        from modules.agents.providers.registry import get_provider
        info = get_provider("deepseek").info()
        out = {
            "ok": True,
            "provider": "deepseek",
            "chat_models": info.available_chat_models,
            "embedding_models": [],
            "note": "free-tier: deepseek-v4-flash (deepseek-chat = обычный, deepseek-reasoner = thinking)",
        }
        return api_ok(data=out)

    creds = (data.get("credentials") or "").strip()
    if not creds:
        cid = (data.get("client_id") or "").strip()
        csec = (data.get("client_secret") or "").strip()
        if cid and csec:
            creds = base64.b64encode(f"{cid}:{csec}".encode()).decode()
    if not creds:
        creds = _agent_credentials()
    if not creds:
        return api_error(
            "agent_credentials_required",
            "Ключ не передан. Введите токен в окне и нажмите «Применить», либо задайте .key / GIGACHAT_CREDENTIALS на сервере.",
            http_status=400,
        )
    scope = (data.get("scope") or "").strip()
    verify_ssl = data.get("verify_ssl")
    vssl: Optional[bool] = None if verify_ssl is None else bool(verify_ssl)
    _ensure_event_loop()
    try:
        from modules.agents.gigachat_agent import probe_models_availability
        out = probe_models_availability(
            _agent_credentials(creds),
            scope_override=_agent_scope(scope),
            verify_ssl_override=vssl,
        )
        return api_ok(data=out)
    except Exception as e:
        return api_error("agent_probe_models_failed", str(e).strip() or type(e).__name__, http_status=500)


@bp.route("/api/agent/profiles", methods=["GET"])
def api_agent_profiles_get():
    """Получить список профилей из agent_profiles.json."""
    profiles = _load_agent_profiles()
    return api_ok(data=profiles, items=profiles)


@bp.route("/api/agent/profiles", methods=["POST"])
def api_agent_profiles_post():
    """Сохранить профили в agent_profiles.json."""
    try:
        data = expect_list_payload(
            request.get_json(force=True, silent=True),
            code="invalid_profiles_payload",
            message="Ожидается массив профилей",
        )
    except RequestValidationError as exc:
        return api_error(exc.code, exc.message, http_status=400)
    existing = _load_agent_profiles()
    existing_by_name = {p.get("name"): p for p in existing if isinstance(p, dict) and p.get("name")}
    profiles = []
    for p in data:
        if isinstance(p, dict) and p.get("name"):
            name = str(p.get("name", "")).strip()
            item: Dict[str, Any] = {
                "name": name,
                "clientId": str(p.get("clientId", "")).strip(),
                "scope": str(p.get("scope", "GIGACHAT_API_PERS")).strip() or "GIGACHAT_API_PERS",
            }
            if p.get("tokenFromEnv"):
                item["tokenFromEnv"] = True
            if p.get("sourceProfile"):
                item["sourceProfile"] = str(p.get("sourceProfile", "")).strip()
            elif name in existing_by_name and existing_by_name[name].get("tokenFromEnv"):
                item["tokenFromEnv"] = True
            if name in existing_by_name and existing_by_name[name].get("sourceProfile"):
                item["sourceProfile"] = existing_by_name[name]["sourceProfile"]
            for model_key in ("chatModel", "embeddingModel"):
                if model_key in p:
                    mv = str(p.get(model_key) or "").strip()
                    if mv:
                        item[model_key] = mv
                elif name in existing_by_name and existing_by_name[name].get(model_key):
                    item[model_key] = existing_by_name[name][model_key]
            profiles.append(item)
    _save_agent_profiles(profiles)
    return api_ok()


# ---------------------------------------------------------------------------
# Generic simple-provider profile routes  (deepseek, groq, openrouter, …)
# New providers are handled automatically — no extra routes needed.
# ---------------------------------------------------------------------------

def _resolve_simple_provider(provider_id: str):
    """Validate provider_id and return its ProviderInfo, or None if invalid/gigachat."""
    try:
        from modules.agents.providers.registry import get_provider
        p = get_provider(provider_id)
        info = p.info()
        return info if info.id != "gigachat" else None
    except Exception:
        return None


@bp.route("/api/agent/profiles/<provider_id>", methods=["GET"])
def api_simple_profiles_get(provider_id: str):
    """Получить список профилей для любого simple-провайдера."""
    from web.context import _load_simple_profiles as _lsp
    info = _resolve_simple_provider(provider_id)
    if info is None:
        return api_error("unknown_provider", f"Провайдер '{provider_id}' не найден или не поддерживается", http_status=404)
    profiles = _lsp(provider_id)
    return api_ok(data=profiles, items=profiles)


@bp.route("/api/agent/profiles/<provider_id>", methods=["POST"])
def api_simple_profiles_post(provider_id: str):
    """Сохранить или обновить профиль для любого simple-провайдера."""
    from web.context import _simple_profile_upsert as _spu
    info = _resolve_simple_provider(provider_id)
    if info is None:
        return api_error("unknown_provider", f"Провайдер '{provider_id}' не найден или не поддерживается", http_status=404)
    data = read_json_object()
    name = (data.get("name") or "").strip()
    chat_model = (data.get("chat_model") or "").strip()
    api_key_hint = (data.get("api_key_hint") or "").strip()
    if not name:
        return api_error("profile_name_required", "Укажите имя профиля", http_status=400)
    # Validate model against available models; fall back to provider default
    allowed = info.available_chat_models
    if allowed and chat_model not in allowed:
        chat_model = info.default_chat_model
    profile = _spu(provider_id, name, chat_model, api_key_hint=api_key_hint)
    return api_ok(data=profile)


@bp.route("/api/agent/profiles/<provider_id>/<name>", methods=["DELETE"])
def api_simple_profiles_delete(provider_id: str, name: str):
    """Удалить профиль по имени для любого simple-провайдера."""
    from web.context import _simple_profile_delete as _spd
    info = _resolve_simple_provider(provider_id)
    if info is None:
        return api_error("unknown_provider", f"Провайдер '{provider_id}' не найден или не поддерживается", http_status=404)
    deleted = _spd(provider_id, name)
    if not deleted:
        return api_error("profile_not_found", f"Профиль '{name}' не найден", http_status=404)
    return api_ok(deleted=True)


@bp.route("/api/agent/model-options", methods=["GET"])
def api_agent_model_options():
    """Список имён чат- и embedding-моделей для выбора в UI."""
    provider = (request.args.get("provider") or "gigachat").strip().lower()
    try:
        if provider != "gigachat":
            from modules.agents.providers.registry import get_provider
            try:
                info = get_provider(provider).info()
                return api_ok(data={"chat": info.available_chat_models, "embedding": [], "provider": provider})
            except Exception:
                pass
        from modules.agents.gigachat_agent import CHAT_MODEL_PRIORITY, EMBEDDING_MODEL_PRIORITY
        return api_ok(
            data={
                "chat": list(CHAT_MODEL_PRIORITY),
                "embedding": list(EMBEDDING_MODEL_PRIORITY),
                "provider": provider,
            }
        )
    except Exception as e:
        return api_error("agent_model_options_failed", str(e).strip() or type(e).__name__, http_status=500)


_PROVIDER_ENV_KEYS = {
    "gigachat": "GIGACHAT_TOKEN",
    "deepseek": "DEEPSEEK_TOKEN",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

_PROVIDER_KEY_PLACEHOLDER = {
    "gigachat": "Base64-токен из личного кабинета GigaChat",
    "deepseek": "sk-… (ключ DeepSeek)",
    "groq": "gsk_… (ключ Groq)",
    "openrouter": "sk-or-… (ключ OpenRouter)",
}

_PROVIDER_DOCS_URL = {
    "groq": "https://console.groq.com",
    "openrouter": "https://openrouter.ai/keys",
    "deepseek": "https://platform.deepseek.com",
}


@bp.route("/api/agent/providers", methods=["GET"])
def api_agent_providers():
    """Список LLM-провайдеров и метаданных из governance manifest."""
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
        return api_ok(data={"providers": items, "supported": list(SUPPORTED_PROVIDERS)})
    except Exception as e:
        return api_error("agent_providers_failed", str(e).strip() or type(e).__name__, http_status=500)


@bp.route("/api/agent/governance", methods=["GET"])
def api_agent_governance():
    """Governance manifest summary (roles, steps, multi-agent policy)."""
    stack = (request.args.get("stack") or "greenplum").strip().lower()
    try:
        from modules.agents.governance.loader import governance_public_summary
        return api_ok(data=governance_public_summary(stack))
    except Exception as e:
        return api_error("agent_governance_failed", str(e).strip() or type(e).__name__, http_status=500)


@bp.route("/api/agent/credentials", methods=["POST"])
def api_agent_credentials():
    """Ключ не сохраняется на сервере — передаётся с каждым запросом."""
    return api_ok()


@bp.route("/api/agent/generate", methods=["POST"])
def api_agent_generate():
    """Backward-compat proxy: бизнес-логика идёт через modules.agents.track."""
    _ensure_event_loop()
    data = read_json_object()
    try:
        description = require_non_empty_string(data, "description", code="description_required")
    except RequestValidationError as exc:
        return api_error(exc.code, "Не передано описание", http_status=400)

    creds = (data.get("credentials") or "").strip()
    if not creds:
        cid = (data.get("client_id") or "").strip()
        csec = (data.get("client_secret") or "").strip()
        if cid and csec:
            creds = base64.b64encode(f"{cid}:{csec}".encode()).decode()

    provider = _agent_provider_from(data)
    stack = _agent_stack_from(data)
    use_env = data.get("use_env_credentials") is True

    if not creds and not use_env:
        return api_error(
            "agent_credentials_required",
            "Ключ не передан. Введите ключ в модальном окне «Ввести ключ» и нажмите «Применить».",
            http_status=503,
        )
    if not creds:
        creds = _resolve_agent_credentials(provider, use_env=use_env)
    if not creds:
        key_hint = "DEEPSEEK_TOKEN" if provider == "deepseek" else "GIGACHAT_CREDENTIALS"
        return api_error(
            "agent_credentials_not_found",
            f"Ключ не найден в .key ({key_hint}). Введите ключ вручную в модальном окне.",
            http_status=503,
        )

    scope = _agent_scope((data.get("scope") or "").strip())
    chat_model = (data.get("chat_model") or data.get("agent_chat_model") or "").strip() or None
    with_review = data.get("with_review") is True
    code_revision_pass = data.get("code_revision_pass") is not False

    try:
        from modules.agents.track import generate_sql as track_generate_sql
        gen = track_generate_sql(
            description,
            provider=provider,
            stack=stack,
            credentials_override=creds,
            model_override=chat_model,
            scope_override=scope,
            with_review=with_review,
            code_revision_pass=code_revision_pass,
            multi_agent=_agent_multi_agent_from(data),
        )
        return api_ok(data=gen, **gen)
    except Exception as e:
        err_str = str(e)
        err_lower = err_str.lower()
        if "429" in err_str or "Too Many Requests" in err_str:
            return api_error(
                "agent_rate_limited",
                "Превышен лимит запросов GigaChat (429). Подождите и повторите.",
                http_status=429,
                rate_limit_429=True,
            )
        if (
            "read operation timed out" in err_lower
            or "readtimeout" in err_lower.replace(" ", "")
            or ("timed out" in err_lower and "operation" in err_lower)
            or "connecttimeout" in err_lower.replace(" ", "")
        ):
            return api_error(
                "agent_generate_timeout",
                "Таймаут ответа GigaChat. В .env задайте GIGACHAT_HTTP_TIMEOUT_SEC (сек.) или GIGACHAT_TIMEOUT_SEC.",
                http_status=504,
            )
        return api_error("agent_generate_failed", err_str, http_status=500)


@bp.route("/api/agent/flow/plan", methods=["GET"])
def api_agent_flow_plan():
    """Построить FlowPlan для UI wizard агента (single / multi-agent)."""
    mode = (request.args.get("mode") or "single").strip().lower()
    stack = (request.args.get("stack") or "greenplum").strip().lower()
    provider = (request.args.get("provider") or "gigachat").strip().lower()
    selected_ids_raw = request.args.getlist("providers")
    try:
        from modules.agents.flow.factory import build_flow_plan, flow_plan_to_dict
        plan = build_flow_plan(
            mode=mode,
            stack=stack,
            provider=provider,
            selected_provider_ids=selected_ids_raw or None,
        )
        return api_ok(data=flow_plan_to_dict(plan))
    except Exception as e:
        return api_error("agent_flow_plan_failed", str(e).strip() or type(e).__name__, http_status=500)


@bp.route("/api/agent/flow/validate-step", methods=["POST"])
def api_agent_flow_validate_step():
    """Валидация шага PROFILE (credentials + model) в UI wizard."""
    data = read_json_object()
    provider_id = _agent_provider_from(data)
    try:
        from modules.agents.flow.contracts import ProfilePayload
        from modules.agents.flow.profile_handlers import get_profile_handler

        payload = ProfilePayload(
            provider_id=provider_id,
            credentials=(data.get("credentials") or "").strip() or None,
            scope=(data.get("scope") or "").strip() or None,
            client_id=(data.get("client_id") or "").strip() or None,
            verify_ssl=data.get("verify_ssl", True),
            use_env_credentials=bool(data.get("use_env_credentials")),
            chat_model=(data.get("chat_model") or "").strip() or None,
            embedding_model=(data.get("embedding_model") or "").strip() or None,
            profile_name=(data.get("profile_name") or "").strip() or None,
        )
        _ensure_event_loop()
        result = get_profile_handler(provider_id).validate(payload)
        if result.ok:
            return api_ok(valid=True, provider_id=result.provider_id, from_env=result.from_env)
        return api_error("agent_flow_validate_failed", result.error or "Ошибка валидации", valid=False)
    except Exception as e:
        return api_error("agent_flow_validate_error", str(e).strip() or type(e).__name__, http_status=500)
