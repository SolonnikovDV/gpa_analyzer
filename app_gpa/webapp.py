#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import hmac
import io
import json
import os
import re
import queue
import time
from contextlib import redirect_stdout
from datetime import datetime
from typing import Dict, Any, List, Optional

from app_settings import PROJECT_ROOT, WEBAPP_DIR, settings

# Базовое состояние зашито в ядре — при старте применяем baseline (из файла или из ядра)
try:
    from agent.agent_cache_db import restore_baseline_config
    restore_baseline_config()
except Exception:
    pass

from flask import Flask, render_template, request, redirect, url_for, Response, jsonify, session, send_file, g
from jinja2 import ChoiceLoader, FileSystemLoader
from werkzeug.exceptions import RequestEntityTooLarge

from detailed.detailed_analyzer import DetailedGreenplumFunctionAnalyzer
from detailed.analysis_handlers import (
    build_analysis_runtime_context,
    build_discovery_runtime_context,
    log_runtime_execution_banner,
)
from detailed.api_contracts import api_error, api_ok, read_json_object
from detailed.analysis_orchestrator import AnalysisOrchestrator
from detailed.job_contracts import (
    JOB_STATUS_DONE,
    JOB_STATUS_ERROR,
    JOB_STATUS_NOT_FOUND,
    JOB_STATUS_RUNNING,
    JOB_STATUS_TABLES_DISCOVERED,
)
from detailed.job_store import JobStore
from detailed.job_runner import create_job_runner
from detailed.job_service import JobService
from detailed.lint.factory import get_linter
from detailed.observability import check_redis_health, check_sqlite_health, generate_request_id, log_event
from detailed.persistence_service import PersistenceService
from detailed.performance_monitor import PerformanceMonitor
from detailed.request_validation import RequestValidationError, expect_list_payload, require_non_empty_string
from detailed.runtime_registry import (
    get_runtime_descriptor,
    get_supported_scenarios,
    get_supported_stacks,
    normalize_scenario,
    normalize_stack,
)
from detailed.security import InMemoryRateLimiter
from detailed.sql_validator import (
    CompositeSQLMetadataProvider,
    OfflineFunctionRegistryProvider,
    PostgresMetadataProvider,
)

app = Flask(__name__)
app.secret_key = settings.secret_key
app.config["MAX_CONTENT_LENGTH"] = settings.max_content_length_bytes
app.config["SESSION_COOKIE_HTTPONLY"] = settings.session_cookie_httponly
app.config["SESSION_COOKIE_SECURE"] = settings.session_cookie_secure
app.config["SESSION_COOKIE_SAMESITE"] = settings.session_cookie_samesite
app.config["PERMANENT_SESSION_LIFETIME"] = settings.session_lifetime

if not settings.flask_debug and settings.uses_default_secret_key:
    raise RuntimeError("APP_SECRET_KEY must be set for non-debug mode.")
if settings.basic_auth_username and not settings.basic_auth_password:
    raise RuntimeError("APP_BASIC_AUTH_PASSWORD must be set when APP_BASIC_AUTH_USERNAME is configured.")
if settings.basic_auth_password and not settings.basic_auth_username:
    raise RuntimeError("APP_BASIC_AUTH_USERNAME must be set when APP_BASIC_AUTH_PASSWORD is configured.")

# Добавляем пути для шаблонов
app.jinja_loader = ChoiceLoader([
    FileSystemLoader('templates'),
    FileSystemLoader('detailed/templates')
])

# Информация об приложении для модального окна «О приложении»
@app.context_processor
def inject_app_info():
    return {
        'app_name': settings.app_name,
        'app_author': settings.app_author,
        'app_version': settings.app_version,
        'app_description': settings.app_description,
        'app_year': datetime.now().year,
    }


try:
    from agent.gigachat_agent import is_agent_available, generate_sql_from_description, generate_sql_with_review
except ImportError:
    is_agent_available = lambda: False
    generate_sql_from_description = None
    generate_sql_with_review = None


def _agent_credentials_from_key_file() -> Optional[str]:
    """Читает токен из .key в корне проекта. Поддерживает: GIGACHAT_TOKEN=..., GIGACHAT_CREDENTIALS=..., или строка base64."""
    _b64_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
    for _d in (PROJECT_ROOT, WEBAPP_DIR):
        key_path = os.path.join(_d, ".key")
        if os.path.isfile(key_path):
            try:
                with open(key_path, "r", encoding="utf-8") as f:
                    lines = [ln.strip() for ln in f.read().splitlines() if ln.strip()]
                for ln in lines:
                    if "=" in ln and ln.startswith(("GIGACHAT_TOKEN=", "GIGACHAT_CREDENTIALS=")):
                        val = ln.split("=", 1)[1].strip()
                        if val:
                            return val
                    if len(ln) >= 32 and all(c in _b64_chars for c in ln):
                        return ln
                return lines[0] if lines else None
            except Exception:
                pass
    return None


def _agent_credentials(override: Optional[str] = None):
    """Ключ агента: override (из запроса) или .key или .env."""
    if override and str(override).strip():
        return override.strip()
    return (
        _agent_credentials_from_key_file()
        or os.environ.get("GIGACHAT_CREDENTIALS")
        or os.environ.get("GIGACHAT_TOKEN")
        or _agent_credentials_from_client_id_secret()
    )


def _agent_credentials_from_client_id_secret():
    """Собирает credentials из GIGACHAT_CLIENT_ID + GIGACHAT_CLIENT_SECRET."""
    cid = os.environ.get("GIGACHAT_CLIENT_ID", "").strip()
    csec = os.environ.get("GIGACHAT_CLIENT_SECRET", "").strip()
    if cid and csec:
        import base64
        return base64.b64encode(f"{cid}:{csec}".encode()).decode()
    return None


def _agent_scope(override: Optional[str] = None):
    """Scope агента: override (из запроса) или .env."""
    if override and str(override).strip():
        return override.strip()
    return os.environ.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")


def _agent_chat_model_from(data: Optional[Dict[str, Any]]) -> Optional[str]:
    if not data:
        return None
    m = (data.get("agent_chat_model") or "").strip()
    return m or None


def _agent_embedding_model_from(data: Optional[Dict[str, Any]]) -> Optional[str]:
    if not data:
        return None
    m = (data.get("agent_embedding_model") or "").strip()
    return m or None


@app.route('/api/agent/env-token-status', methods=['GET'])
def api_agent_env_token_status():
    """Проверка наличия токена в .key или .env (без раскрытия значения)."""
    creds = _agent_credentials()
    return api_ok(hasToken=bool(creds))


@app.route('/api/agent/validate-env', methods=['POST'])
def api_agent_validate_env():
    """Проверка валидности токена из .key или .env."""
    creds = _agent_credentials()
    if not creds:
        return api_error(
            "agent_credentials_missing",
            "Токен не задан. Добавьте в .key (корень проекта) или в .env: GIGACHAT_CREDENTIALS / GIGACHAT_TOKEN.",
            http_status=400,
            valid=False,
        )
    _ensure_event_loop()
    try:
        from agent.gigachat_agent import validate_credentials
        data = read_json_object()
        scope = (data.get("scope") or "").strip() or _agent_scope()
        validate_credentials(credentials_override=creds, scope_override=scope)
        return api_ok(valid=True)
    except Exception as e:
        return api_error("agent_validate_env_failed", str(e), valid=False)


@app.route('/api/agent/status', methods=['GET', 'POST'])
def api_agent_status():
    """Проверка доступности режима агента (GigaChat): ключ из запроса (JSON) или .env."""
    creds = None
    scope = None
    if request.method == 'POST':
        data = read_json_object()
        creds = (data.get("credentials") or "").strip()
        cid = (data.get("client_id") or "").strip()
        csec = (data.get("client_secret") or "").strip()
        if cid and csec:
            import base64
            creds = base64.b64encode(f"{cid}:{csec}".encode()).decode()
        scope = (data.get("scope") or "").strip()
    return api_ok(available=bool(_agent_credentials(creds)) and (generate_sql_from_description is not None))


@app.route('/api/agent/token_usage', methods=['GET', 'POST'])
def api_agent_token_usage():
    """Использованные токены и (при пакетной оплате) доступный остаток. Ключ из запроса (JSON) или .env."""
    creds = None
    scope = None
    if request.method == 'POST':
        data = read_json_object()
        creds = (data.get("credentials") or "").strip()
        cid = (data.get("client_id") or "").strip()
        csec = (data.get("client_secret") or "").strip()
        if cid and csec:
            import base64
            creds = base64.b64encode(f"{cid}:{csec}".encode()).decode()
        scope = (data.get("scope") or "").strip()
    try:
        from agent.gigachat_agent import get_token_usage
        data = get_token_usage(credentials_override=_agent_credentials(creds), scope_override=_agent_scope(scope))
        return api_ok(data=data, **data)
    except Exception:
        fallback = {"used": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "available": None}
        return api_ok(data=fallback, **fallback)


@app.route('/api/agent/tokens_count', methods=['POST'])
def api_agent_tokens_count():
    """POST /tokens/count: подсчёт токенов в строках (массив input + model). Документация GigaChat REST."""
    data = read_json_object()
    raw_input = data.get("input")
    if raw_input is None:
        raw_input = data.get("inputs")
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
        import base64
        creds = base64.b64encode(f"{cid}:{csec}".encode()).decode()
    scope = (data.get("scope") or "").strip()
    try:
        from agent.gigachat_agent import count_input_tokens
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


def _mask_secret(s: str) -> str:
    """Маскирует секреты для логов — ключ никогда не выводится в явном виде."""
    if not s or not isinstance(s, str):
        return ""
    masked = str(s)
    secret_field_pattern = r"(?i)\b(" + "|".join(("pass" + "word", "passwd", "token", "credentials", "client_secret")) + r")\s*[:=]\s*([^\s,;]+)"
    conn_password_pattern = r"(?i)\b(user=\S+\s+" + "pass" + r"word=)(\S+)"
    masked = re.sub(
        secret_field_pattern,
        lambda match: f"{match.group(1)}=***",
        masked,
    )
    masked = re.sub(conn_password_pattern, r'\1***', masked)
    masked = re.sub(r'[A-Za-z0-9+/]{32,}={0,2}', "***", masked)
    return masked


def _request_client_identity() -> str:
    forwarded_for = (request.headers.get("X-Forwarded-For") or "").strip()
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or "unknown"
    return request.remote_addr or "unknown"


def _is_request_authorized() -> bool:
    if not settings.basic_auth_enabled:
        return True
    auth = request.authorization
    if not auth:
        return False
    username = auth.username or ""
    password = auth.password or ""
    return hmac.compare_digest(username, settings.basic_auth_username) and hmac.compare_digest(
        password,
        settings.basic_auth_password,
    )


def _unauthorized_response() -> Response:
    response = Response("Authentication required", 401)
    response.headers["WWW-Authenticate"] = 'Basic realm="GPA Analyzer"'
    return response


@app.before_request
def apply_session_baseline():
    g.request_id = (request.headers.get("X-Request-ID") or "").strip() or generate_request_id()
    g.request_started_at = time.time()
    session.permanent = True
    if _is_public_endpoint():
        return None
    log_event(
        "http.request.started",
        request_id=g.request_id,
        method=request.method,
        path=request.path,
        remote_addr=_request_client_identity(),
    )
    if not _is_request_authorized():
        log_event(
            "http.request.unauthorized",
            request_id=g.request_id,
            method=request.method,
            path=request.path,
        )
        return _unauthorized_response()
    if _rate_limiter is not None:
        decision = _rate_limiter.check(_request_client_identity())
        if not decision.allowed:
            log_event(
                "http.request.rate_limited",
                request_id=g.request_id,
                method=request.method,
                path=request.path,
                retry_after_seconds=decision.retry_after_seconds,
            )
            response = api_error(
                "rate_limit_exceeded",
                "Слишком много запросов. Повторите позже.",
                http_status=429,
                retry_after_seconds=decision.retry_after_seconds,
            )
            response.headers["Retry-After"] = str(decision.retry_after_seconds)
            return response
    return None


@app.after_request
def apply_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    request_id = getattr(g, "request_id", "")
    if request_id:
        response.headers.setdefault("X-Request-ID", request_id)
    if request.path.startswith("/api/") or request.path.startswith("/stream/"):
        response.headers.setdefault("Cache-Control", "no-store")
    started_at = getattr(g, "request_started_at", None)
    duration_ms = None
    if started_at is not None:
        duration_ms = int((time.time() - started_at) * 1000)
    log_event(
        "http.request.completed",
        request_id=request_id,
        method=request.method,
        path=request.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response


@app.errorhandler(RequestEntityTooLarge)
def handle_request_entity_too_large(_error):
    return api_error(
        "request_too_large",
        "Размер запроса превышает допустимый лимит.",
        http_status=413,
        max_content_length_bytes=settings.max_content_length_bytes,
    )


@app.route("/health/live", methods=["GET"])
def health_live():
    payload = {"status": "live", "checks": {"app": {"ok": True}}}
    return api_ok(data=payload, **payload)


@app.route("/health/ready", methods=["GET"])
@app.route("/health", methods=["GET"])
def health_ready():
    checks = {
        "sqlite": check_sqlite_health(_persistence.db_path),
    }
    if settings.job_runner_backend == "queue":
        checks["redis"] = check_redis_health(settings.redis_url)
    else:
        checks["queue_backend"] = {"ok": True, "backend": settings.job_runner_backend, "mode": "local"}

    overall_ok = all(bool(item.get("ok")) for item in checks.values())
    payload = {
        "status": "ready" if overall_ok else "degraded",
        "checks": checks,
    }
    return api_ok(data=payload, http_status=200 if overall_ok else 503, **payload)


def _ensure_event_loop():
    """В worker-потоке GigaChat SDK требует event loop. Создаём его, если нет или он закрыт."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


@app.route('/api/agent/validate', methods=['POST'])
def api_agent_validate():
    """Проверка валидности кредов подключения к GigaChat API."""
    data = read_json_object()
    creds = (data.get("credentials") or "").strip()
    scope = (data.get("scope") or "").strip()
    verify_ssl = data.get("verify_ssl")
    if verify_ssl is None:
        verify_ssl = True
    else:
        verify_ssl = bool(verify_ssl)
    if not creds:
        return api_error("agent_token_missing", "Не указан Token", http_status=400, valid=False)
    _ensure_event_loop()
    try:
        from agent.gigachat_agent import validate_credentials
        validate_credentials(
            credentials_override=_agent_credentials(creds),
            scope_override=_agent_scope(scope),
            verify_ssl_override=verify_ssl,
        )
        return api_ok(valid=True)
    except Exception as e:
        err_msg = str(e).strip() or "Неизвестная ошибка"
        err_lower = err_msg.lower()
        is_ssl = (
            "ssl" in err_lower or "certificate" in err_lower or "eof" in err_lower or "protocol" in err_lower
            or "connection reset" in err_lower or "reset by peer" in err_lower
        )
        if is_ssl and verify_ssl:
            try:
                validate_credentials(
                    credentials_override=_agent_credentials(creds),
                    scope_override=_agent_scope(scope),
                    verify_ssl_override=False,
                )
                os.environ["GIGACHAT_VERIFY_SSL_CERTS"] = "false"
                return api_ok(valid=True, verify_ssl_used=False)
            except Exception:
                pass
        if is_ssl:
            if not verify_ssl:
                err_msg = f"{err_msg} — проверка SSL уже отключена. Проверьте сеть, firewall, прокси."
            elif "connection reset" in err_lower or "reset by peer" in err_lower:
                err_msg = (
                    f"{err_msg} — соединение сброшено удалённой стороной (часто из‑за SSL/прокси/фаервола). "
                    "Снимите галочку «Проверять SSL-сертификат» и нажмите «Применить», или задайте GIGACHAT_VERIFY_SSL_CERTS=false в .env. "
                    "Проверьте доступность API с этой машины: curl -k https://api.sber.ru или check_gigachat_connection.py --no-ssl-verify."
                )
            elif "timeout" in err_lower or "timed out" in err_lower or "handshake" in err_lower:
                err_msg = (
                    f"{err_msg} — таймаут подключения к API. Снимите галочку «Проверять SSL-сертификат» "
                    "или добавьте GIGACHAT_VERIFY_SSL_CERTS=false в .env."
                )
            else:
                err_msg = (
                    f"{err_msg} — снимите галочку «Проверять SSL-сертификат» и нажмите «Применить» снова, "
                    "или добавьте GIGACHAT_VERIFY_SSL_CERTS=false в .env и перезапустите приложение."
                )
        elif "auth" in err_lower or "401" in err_msg or "unauthorized" in err_lower:
            err_msg = f"Неверные креды: {err_msg}"
        elif "event loop" in err_lower:
            err_msg = f"{err_msg} (внутренняя ошибка — перезапустите приложение)"
        return api_error("agent_validate_failed", err_msg, http_status=401, valid=False)


@app.route("/api/agent/probe-models", methods=["POST"])
def api_agent_probe_models():
    """Проверка доступности чат- и embedding-моделей (для информационного модала в UI)."""
    data = read_json_object()
    creds = (data.get("credentials") or "").strip()
    if not creds:
        cid = (data.get("client_id") or "").strip()
        csec = (data.get("client_secret") or "").strip()
        if cid and csec:
            import base64

            creds = base64.b64encode(f"{cid}:{csec}".encode()).decode()
    # Как validate-env: если в теле нет ключа (часто — кнопка «Проверить» до «Применить»),
    # берём .key / .env на сервере. Явный credentials в теле имеет приоритет.
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
    if verify_ssl is None:
        vssl: Optional[bool] = None
    else:
        vssl = bool(verify_ssl)
    _ensure_event_loop()
    try:
        from agent.gigachat_agent import probe_models_availability

        out = probe_models_availability(
            _agent_credentials(creds),
            scope_override=_agent_scope(scope),
            verify_ssl_override=vssl,
        )
        return api_ok(data=out)
    except Exception as e:
        return api_error("agent_probe_models_failed", str(e).strip() or type(e).__name__, http_status=500)


# Профили GigaChat (Client ID + Scope): файл в проекте для ручного редактирования
_AGENT_PROFILES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'agent_profiles.json')


def _load_agent_profiles() -> List[Dict[str, str]]:
    """Читает профили из agent_profiles.json."""
    try:
        if os.path.isfile(_AGENT_PROFILES_PATH):
            with open(_AGENT_PROFILES_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _save_agent_profiles(profiles: List[Dict[str, str]]) -> None:
    """Сохраняет профили в agent_profiles.json."""
    with open(_AGENT_PROFILES_PATH, 'w', encoding='utf-8') as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)


@app.route('/api/agent/profiles', methods=['GET'])
def api_agent_profiles_get():
    """Получить список профилей (Client ID + Scope) из agent_profiles.json."""
    profiles = _load_agent_profiles()
    return api_ok(data=profiles, items=profiles)


@app.route('/api/agent/profiles', methods=['POST'])
def api_agent_profiles_post():
    """Сохранить профили в agent_profiles.json. Тело: [{ name, clientId, scope, tokenFromEnv?, sourceProfile? }, ...]."""
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
            item = {
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
            if "chatModel" in p:
                cm = str(p.get("chatModel") or "").strip()
                if cm:
                    item["chatModel"] = cm
            elif name in existing_by_name and existing_by_name[name].get("chatModel"):
                item["chatModel"] = existing_by_name[name]["chatModel"]
            if "embeddingModel" in p:
                em = str(p.get("embeddingModel") or "").strip()
                if em:
                    item["embeddingModel"] = em
            elif name in existing_by_name and existing_by_name[name].get("embeddingModel"):
                item["embeddingModel"] = existing_by_name[name]["embeddingModel"]
            profiles.append(item)
    _save_agent_profiles(profiles)
    return api_ok()


@app.route("/api/agent/model-options", methods=["GET"])
def api_agent_model_options():
    """Список имён чат- и embedding-моделей (как в gigachat_agent), для выбора в UI."""
    try:
        from agent.gigachat_agent import CHAT_MODEL_PRIORITY, EMBEDDING_MODEL_PRIORITY

        return api_ok(
            data={
                "chat": list(CHAT_MODEL_PRIORITY),
                "embedding": list(EMBEDDING_MODEL_PRIORITY),
            }
        )
    except Exception as e:
        return api_error("agent_model_options_failed", str(e).strip() or type(e).__name__, http_status=500)


@app.route('/api/agent/credentials', methods=['POST'])
def api_agent_credentials():
    """Ключ не сохраняется на сервере. Вводится в UI и передаётся с каждым запросом."""
    return api_ok()


@app.route('/api/agent/generate', methods=['POST'])
def api_agent_generate():
    """Генерация SQL/функции по текстовому описанию через GigaChat.
    При with_review=True — анализ описания, предупреждение и SQL; по умолчанию второй проход модели (ревизия кода).
    Отключить ревизию: code_revision_pass=false (экономия токенов)."""
    _ensure_event_loop()
    data = read_json_object()
    try:
        description = require_non_empty_string(data, "description", code="description_required")
    except RequestValidationError as exc:
        return api_error(exc.code, "Не передано описание", http_status=400)
    with_review = data.get("with_review") is True
    code_revision_pass = data.get("code_revision_pass") is not False
    creds = (data.get("credentials") or "").strip()
    if not creds:
        cid, csec = (data.get("client_id") or "").strip(), (data.get("client_secret") or "").strip()
        if cid and csec:
            import base64
            creds = base64.b64encode(f"{cid}:{csec}".encode()).decode()
    use_env = data.get("use_env_credentials") is True
    if not creds and not use_env:
        return api_error(
            "agent_credentials_required",
            "Ключ не передан. Введите ключ в модальном окне «Ввести ключ» и нажмите «Применить».",
            http_status=503,
        )
    if not creds and use_env:
        creds = _agent_credentials()
    if not creds:
        return api_error(
            "agent_credentials_not_found",
            "Ключ не найден в .key. Введите ключ вручную в модальном окне.",
            http_status=503,
        )
    scope = _agent_scope((data.get("scope") or "").strip())
    chat_model = (data.get("chat_model") or data.get("agent_chat_model") or "").strip() or None
    if generate_sql_from_description is None:
        return api_error("agent_generate_unavailable", "Модуль генерации недоступен.", http_status=503)
    try:
        if with_review and generate_sql_with_review is not None:
            result = generate_sql_with_review(
                description,
                credentials_override=creds,
                model_override=chat_model,
                code_revision_pass=code_revision_pass,
            )
            payload = {
                "sql_or_ddl": result.get("sql_or_ddl", ""),
                "warning": result.get("warning"),
                "analysis": result.get("analysis"),
                "revision_applied": bool(result.get("revision_applied")),
                "code_revision_ran": bool(result.get("code_revision_ran")),
            }
            return api_ok(data=payload, **payload)
        sql_or_ddl = generate_sql_from_description(
            description,
            credentials_override=creds,
            model_override=chat_model,
        )
        return api_ok(data={"sql_or_ddl": sql_or_ddl}, sql_or_ddl=sql_or_ddl)
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
                "Таймаут ответа GigaChat. В .env задайте GIGACHAT_HTTP_TIMEOUT_SEC (сек., приоритет) или "
                "GIGACHAT_TIMEOUT_SEC — таймаут HTTP-клиента SDK (по умолчанию 180 с; у SDK из коробки ~30 с).",
                http_status=504,
            )
        return api_error("agent_generate_failed", err_str, http_status=500)


@app.route('/api/sql/validate', methods=['POST'])
def api_sql_validate():
    """Stack-aware advisory linting with GreenPlum default compatibility."""
    data = read_json_object()
    source_text = data.get("source_text") or data.get("sql") or ""
    stack = normalize_stack(data.get("stack"))
    scenario = normalize_scenario(data.get("scenario") or data.get("validation_mode"))
    runtime_descriptor = get_runtime_descriptor(stack, scenario)
    linter = get_linter(stack)
    offline_provider = OfflineFunctionRegistryProvider()
    metadata_provider = offline_provider
    user = (data.get("user") or "").strip()
    password = (data.get("password") or "").strip()
    if runtime_descriptor.capabilities.supports_catalog_metadata and user and password:
        stand_type = (data.get("stand_type") or "").strip() or "PROM"
        host = (data.get("host") or "").strip() or None
        dbname = (data.get("dbname") or "").strip() or None
        port = data.get("port")
        if port is not None and port != "":
            try:
                port = int(port)
            except (TypeError, ValueError):
                port = None
        else:
            port = None
        try:
            conn_string = _build_conn_string(stand_type, user, password, host, port, dbname)
            metadata_provider = CompositeSQLMetadataProvider([
                PostgresMetadataProvider(conn_string),
                offline_provider,
            ])
        except Exception:
            metadata_provider = offline_provider
    result = linter.validate(source_text, scenario=scenario, metadata_provider=metadata_provider)
    return api_ok(data=result, **result)


@app.route('/api/sql/complete', methods=['POST'])
def api_sql_complete():
    """Stack-aware completion with GreenPlum default compatibility."""
    data = read_json_object()
    source_text = data.get("source_text") or data.get("sql") or ""
    stack = normalize_stack(data.get("stack"))
    scenario = normalize_scenario(data.get("scenario") or data.get("validation_mode"))
    runtime_descriptor = get_runtime_descriptor(stack, scenario)
    linter = get_linter(stack)
    cursor_index = data.get("cursor_index")
    try:
        cursor_index = int(cursor_index)
    except (TypeError, ValueError):
        cursor_index = len(source_text)
    conn_string = None
    user = (data.get("user") or "").strip()
    password = (data.get("password") or "").strip()
    if runtime_descriptor.capabilities.supports_catalog_metadata and user and password:
        stand_type = (data.get("stand_type") or "").strip() or "PROM"
        host = (data.get("host") or "").strip() or None
        dbname = (data.get("dbname") or "").strip() or None
        port = data.get("port")
        if port is not None and port != "":
            try:
                port = int(port)
            except (TypeError, ValueError):
                port = None
        else:
            port = None
        try:
            conn_string = _build_conn_string(stand_type, user, password, host, port, dbname)
        except Exception:
            conn_string = None
    result = linter.complete(source_text, cursor_index, scenario=scenario, conn_string=conn_string)
    return api_ok(data=result, **result)


@app.route('/api/runtime/descriptor', methods=['GET', 'POST'])
def api_runtime_descriptor():
    """Expose stack/scenario descriptor for future multi-stack UI."""
    payload = read_json_object() if request.method == 'POST' else request.args
    data = payload or {}
    stack = normalize_stack(data.get("stack"))
    scenario = normalize_scenario(data.get("scenario"))
    descriptor = get_runtime_descriptor(stack, scenario)
    result = {
        "stack": descriptor.stack,
        "scenario": descriptor.scenario,
        "descriptor": descriptor.to_dict(),
        "supported_stacks": get_supported_stacks(),
        "supported_scenarios": get_supported_scenarios(),
    }
    return api_ok(data=result, **result)


def _test_runtime_payload(data: Dict[str, Any]) -> tuple[Dict[str, Any], int]:
    stack = normalize_stack(data.get("stack"))
    scenario = normalize_scenario(data.get("scenario"))
    descriptor = get_runtime_descriptor(stack, scenario)

    if stack == "greenplum":
        stand_type = (data.get("stand_type") or "").strip() or "PROM"
        user = (data.get("user") or "").strip()
        password = (data.get("password") or "").strip()
        host = (data.get("host") or "").strip() or None
        port = data.get("port")
        if port is not None and port != "":
            try:
                port = int(port)
            except (TypeError, ValueError):
                port = None
        dbname = (data.get("dbname") or "").strip() or None
        if not user or not password:
            return {"ok": False, "error": descriptor.ui.get("connection_missing") or "Не указаны логин и пароль."}, 400
        try:
            conn = _build_conn_string(stand_type, user, password, host, port, dbname)
            import psycopg2
            c = psycopg2.connect(conn)
            c.close()
            return {"ok": True, "message": descriptor.ui.get("connection_success")}, 200
        except Exception as e:
            return {"ok": False, "error": str(e)}, 500

    master_url = (data.get("master_url") or "").strip()
    if not master_url:
        return {"ok": False, "error": descriptor.ui.get("connection_missing") or "Не указан runtime endpoint."}, 400
    return {
        "ok": True,
        "message": descriptor.ui.get("connection_success"),
        "stack": stack,
        "runtime_note": "Runtime test works in MVP mode for this stack and validates access parameters without a native connector.",
    }, 200


@app.route('/api/runtime/test', methods=['POST'])
def api_runtime_test():
    """Stack-aware runtime access test for GreenPlum, Spark and PySpark."""
    data = read_json_object()
    body, status = _test_runtime_payload(data)
    if status >= 400:
        return api_error("runtime_test_failed", str(body.get("error") or "Runtime test failed"), http_status=status, **body)
    return api_ok(data=body, http_status=status, **body)


@app.route('/api/runtime-presets', methods=['GET', 'POST', 'DELETE'])
def api_runtime_presets():
    if request.method == 'GET':
        stack = normalize_stack(request.args.get('stack')) if request.args.get('stack') else None
        kind = (request.args.get('kind') or '').strip().lower() or None
        if stack or kind:
            items = _preset_store.list_presets(stack=stack, kind=kind)
            return api_ok(data={"items": items}, items=items)
        grouped = _preset_store.list_grouped_values()
        return api_ok(data={"grouped": grouped}, grouped=grouped)

    data = read_json_object()
    stack = normalize_stack(data.get('stack'))
    try:
        kind = require_non_empty_string(data, "kind", code="preset_kind_required").lower()
        name = require_non_empty_string(data, "name", code="preset_name_required")
    except RequestValidationError as exc:
        if request.method == 'DELETE':
            return api_error(exc.code, "kind and name are required", http_status=400)
        return api_error(exc.code, "stack, kind and name are required", http_status=400)

    if request.method == 'DELETE':
        deleted = _preset_store.delete_preset(stack, kind, name)
        if not deleted:
            return api_error("preset_not_found", "Preset not found", http_status=404, deleted=False)
        return api_ok(deleted=True)

    value = data.get('value')
    if value is None:
        return api_error("preset_value_required", "Preset value is required", http_status=400)
    try:
        record = _preset_store.upsert_preset(stack, kind, name, str(value))
    except ValueError as exc:
        return api_error("preset_invalid", str(exc), http_status=400)
    return api_ok(data={"preset": record}, preset=record)


@app.route('/license')
def license_page():
    """Отдаёт текст MIT-лицензии из корня проекта."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, 'LICENSE')
    if not os.path.isfile(path):
        return 'License file not found', 404
    return send_file(path, mimetype='text/plain', as_attachment=False, download_name='LICENSE')


@app.route('/api/db/test', methods=['POST'])
def api_db_test():
    """Backward-compatible runtime test endpoint."""
    data = read_json_object()
    if "stack" not in data:
        data["stack"] = "greenplum"
    body, status = _test_runtime_payload(data)
    if status >= 400:
        return api_error("runtime_test_failed", str(body.get("error") or "Runtime test failed"), http_status=status, **body)
    return api_ok(data=body, http_status=status, **body)


@app.route('/api/cache/baseline', methods=['GET'])
def api_cache_baseline_exists():
    """Проверка наличия базового снимка."""
    try:
        from agent.agent_cache_db import baseline_exists
        return api_ok(exists=baseline_exists())
    except Exception:
        return api_ok(exists=False)


@app.route('/api/cache/baseline/save', methods=['POST'])
def api_cache_baseline_save():
    """Сохранить текущее состояние кэшей как базовое. При сбросе данные не будут удаляться ниже этого снимка."""
    try:
        from agent.agent_cache_db import save_baseline
        if save_baseline():
            return api_ok(message="Базовое состояние сохранено")
        return api_error("baseline_save_failed", "Не удалось сохранить", http_status=500)
    except Exception as e:
        return api_error("baseline_save_failed", str(e), http_status=500)


@app.route('/api/cache/reset', methods=['POST'])
def api_cache_reset():
    """
    Сброс кэшей к базовым настройкам.
    Если есть сохранённый baseline — восстанавливает из него (не ниже текущего состояния).
    Иначе — полная очистка.
    Тело: JSON с полями vector, cache, state (bool) — что сбросить.
    """
    data = read_json_object()
    reset_vector = bool(data.get("vector", False))
    reset_cache = bool(data.get("cache", False))
    reset_state = bool(data.get("state", False))
    if not (reset_vector or reset_cache or reset_state):
        return api_ok(message="Ничего не выбрано для сброса", reset={})
    result = {}
    try:
        from agent.agent_cache_db import reset_vector_cache, reset_agent_cache, reset_state_cache, baseline_exists, restore_baseline_config
        has_baseline = baseline_exists()
        config_restored = restore_baseline_config()
        if config_restored:
            result["config"] = "восстановлено"
        if reset_vector:
            result["vector"] = reset_vector_cache()
        if reset_cache:
            n = reset_agent_cache()
            try:
                from agent.gigachat_agent import reset_agent_cache_memory
                reset_agent_cache_memory()
            except Exception:
                pass
            result["cache"] = n
        if reset_state:
            result["state"] = reset_state_cache()
    except Exception as e:
        return api_error("cache_reset_failed", str(e), http_status=500)
    msg = "Восстановлено из базового снимка" if has_baseline else "Сброс выполнен"
    return api_ok(message=msg, reset=result, from_baseline=has_baseline)


# Default stand presets
STANDS = {
    'PROM': {
        'host': 'gp_dns_gp_rozn4.gp.df.sbrf.ru',
        'port': 5432,
        'dbname': 'gp_rozn2',
    },
    'LD': {
        'host': 'gp_dns_pkap1150.gp.df.sbrf.ru',
        'port': 5432,
        'dbname': 'gp_rozn2',
    },
    'IFT': {
        'host': 'tvlds-sdpgp0478.qa.df.sbrf.ru',
        'port': 5432,
        'dbname': 'iftadbcom',
    },
    'Пользовательский': {
        'host': None,
        'port': None,
        'dbname': None,
    },
}

# In-memory store of running jobs and logs
_persistence = PersistenceService(settings.runtime_store_dir, settings.persistence_db_path)
_job_store: JobStore = _persistence.job_store
_preset_store = _persistence.runtime_preset_store
_jobs: Dict[str, Dict[str, Any]] = _job_store.load_jobs()
_logs: Dict[str, "queue.Queue[str]"] = {}
_performance_monitors: Dict[str, PerformanceMonitor] = {}
_job_service = JobService(_job_store, _jobs, _logs)
_job_runner = create_job_runner(
    settings.job_runner_backend,
    redis_url=settings.redis_url,
    queue_name=settings.job_queue_name,
)
_analysis_orchestrator = AnalysisOrchestrator(_job_service, _performance_monitors, PerformanceMonitor)
_rate_limiter = (
    InMemoryRateLimiter(
        limit=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )
    if settings.rate_limit_enabled
    else None
)

JOB_NOT_FOUND_MESSAGE = "Задача не найдена"
EVENT_JOB_DISCOVERY_COMPLETED = "job.discovery.completed"


def _is_public_endpoint() -> bool:
    return request.endpoint == "static" or request.path.startswith("/health")


def _effective_loader_mode(analysis_mode: str, use_db: bool) -> str:
    if analysis_mode == 'hybrid':
        return 'hybrid' if use_db else 'agent'
    return analysis_mode or 'logic'


def _extract_runtime_analysis_config(data: Dict[str, Any]) -> Dict[str, Any]:
    stack = normalize_stack(data.get('stack'))
    if stack == 'spark':
        return {
            'master_url': data.get('master_url'),
            'catalog': data.get('catalog'),
            'namespace': data.get('namespace'),
            'executor_instances': data.get('executor_instances'),
            'executor_cores': data.get('executor_cores'),
            'executor_memory': data.get('executor_memory'),
            'metadata_json': data.get('spark_metadata_json'),
            'profile_json': data.get('spark_profile_json'),
        }
    if stack == 'pyspark':
        return {
            'master_url': data.get('master_url'),
            'session_name': data.get('session_name'),
            'executor_instances': data.get('pyspark_executor_instances') or data.get('executor_instances'),
            'executor_memory': data.get('pyspark_executor_memory') or data.get('executor_memory'),
            'metadata_json': data.get('pyspark_metadata_json'),
            'profile_json': data.get('pyspark_profile_json'),
        }
    return {
        'stand_type': data.get('stand_type'),
        'host': data.get('host'),
        'port': data.get('port'),
        'dbname': data.get('dbname'),
        'segments': data.get('segments'),
        'ram_per_seg_gb': data.get('ram_per_seg_gb'),
    }


def _apply_runtime_quality_metadata(result: Dict[str, Any], *, stack: str, runtime_descriptor: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    if stack == 'greenplum':
        segments = payload.get('segments')
        ram_per_seg_gb = payload.get('ram_per_seg_gb')
        try:
            cluster_capacity_gb = float(segments) * float(ram_per_seg_gb) * 0.72
        except (TypeError, ValueError):
            cluster_capacity_gb = 0.0
        result.setdefault('runtime_context', {
            'runtime_label': runtime_descriptor.ui.get('stack_label', stack),
            'quality': 'deep',
            'capacity_gb': round(cluster_capacity_gb, 3),
            'notes': ['GreenPlum path использует нативный analyzer и DB-backed discovery/analyze flow.'],
        })
        result.setdefault('analysis_quality', 'deep')
        result.setdefault('cluster_capacity_gb', round(cluster_capacity_gb, 3))
        total_memory_gb = float(result.get('total_memory_gb') or 0.0)
        result.setdefault('memory_pressure', round(total_memory_gb / cluster_capacity_gb, 3) if cluster_capacity_gb > 0 else None)
        return result

    result.setdefault('runtime_context', {
        'runtime_label': runtime_descriptor.ui.get('stack_label', stack),
        'quality': 'approximate',
        'notes': ['Для этого стека используется runtime-hinted analysis без нативного коннектора.'],
    })
    result.setdefault('analysis_quality', result.get('runtime_context', {}).get('quality', 'approximate'))
    result.setdefault('cluster_capacity_gb', 0.0)
    result.setdefault('memory_pressure', None)
    return result


def _build_conn_string(stand_type: str, user: str, password: str, host: Optional[str], port: Optional[int], dbname: Optional[str]) -> str:
    """Формирует строку подключения к Greenplum"""
    preset = STANDS.get(stand_type.upper(), {})
    host_val = host or preset.get('host')
    port_val = port or preset.get('port')
    db_val = dbname or preset.get('dbname')
    return f"dbname={db_val} user={user} password={password} host={host_val} port={port_val}"


def _enqueue_log(job_id: str, text: str):
    """Добавляет сообщение в лог задачи"""
    for line in text.splitlines():
        _job_service.append_log_line(job_id, line)


def _stream_stdout_to_queue(job_id: str):
    """Перенаправляет stdout в очередь логов с немедленной отправкой. Секреты маскируются."""
    class Stream(io.TextIOBase):
        def write(self, s):
            _enqueue_log(job_id, _mask_secret(str(s)))
            # Принудительно сбрасываем буфер
            if hasattr(self, 'flush'):
                self.flush()
            return len(s)
    return Stream()


def _collect_logic_warning_fragments(analyzer: DetailedGreenplumFunctionAnalyzer, source_text: str) -> Dict[str, Any]:
    """Находит фрагменты, которые логика не смогла уверенно классифицировать, но которые похожи на SQL-блоки."""
    from detailed import block_parser

    sql_markers = (
        "SELECT ", "INSERT ", "UPDATE ", "DELETE ", "MERGE ", "WITH ",
        "EXECUTE ", "RETURN QUERY", "CREATE TEMP", "TRUNCATE "
    )
    warnings: List[str] = []
    fragments: List[str] = []
    executable_count = 0

    blocks = list(getattr(analyzer, "blocks", []) or [])
    block_types = list(getattr(analyzer, "block_types", []) or [])

    for idx, block in enumerate(blocks):
        block_type = block_types[idx] if idx < len(block_types) else "OTHER"
        if block_parser.is_executable_sql(block_type):
            executable_count += 1
            continue
        block_text = str(block or "").strip()
        compact_upper = " ".join(block_text.upper().split())
        if block_text and any(marker in compact_upper for marker in sql_markers):
            warnings.append(
                f"Логика пометила фрагмент {idx + 1} как {block_type}; он передан агенту на валидацию логического блока."
            )
            fragments.append(block_text)

    if executable_count == 0:
        warnings.insert(0, "Логика не выделила исполняемые логические блоки; включён агентский fallback.")
        fallback_text = str(source_text or "").strip()
        if fallback_text and not fragments:
            fragments.append(fallback_text)

    return {
        "warnings": warnings,
        "fragments": fragments,
        "executable_count": executable_count,
    }


def _merge_agent_objects_into_discovery(
    analyzer: DetailedGreenplumFunctionAnalyzer,
    result: Dict[str, Any],
    agent_objects: List[str],
) -> int:
    """Добирает статистику по объектам, которые логика пропустила, но агент обнаружил в предупреждённых фрагментах."""
    if not analyzer.conn:
        return 0

    discovered_tables = getattr(analyzer, "discovered_tables", {}) or {}
    view_to_tables_map = getattr(analyzer, "view_to_tables_map", {}) or {}
    physical_tables = getattr(analyzer, "physical_tables", set()) or set()
    added = 0

    for full_name in agent_objects or []:
        raw_name = str(full_name or "").strip()
        if not raw_name:
            continue

        if "." in raw_name:
            schema, table = raw_name.split(".", 1)
        else:
            schema, table = "public", raw_name

        schema = schema.strip().lower()
        table = table.strip().lower()
        if not table:
            continue

        resolved = analyzer._resolve_object_to_tables(schema, table) or set()
        if not resolved:
            resolved = {(schema, table)}

        view_key = f"{schema}.{table}"
        view_to_tables_map.setdefault(view_key, [f"{s}.{t}" for s, t in sorted(resolved)])

        for phys_schema, phys_table in resolved:
            physical_tables.add((phys_schema, phys_table))
            key = f"{phys_schema}.{phys_table}"
            if key in discovered_tables:
                continue

            stats = analyzer._get_real_table_stats(phys_schema, phys_table)
            if stats:
                discovered_tables[key] = {
                    "schema": phys_schema,
                    "table": phys_table,
                    "current_rows": stats.rows_estimate,
                    "size_gb": stats.memory_estimate_gb,
                    "avg_row_size_bytes": stats.avg_row_size_bytes,
                    "columns": stats.columns,
                    "user_rows": stats.rows_estimate,
                }
            else:
                discovered_tables[key] = {
                    "schema": phys_schema,
                    "table": phys_table,
                    "current_rows": 0,
                    "size_gb": 0.0,
                    "avg_row_size_bytes": 0,
                    "columns": 0,
                    "user_rows": 0,
                }
            added += 1

    analyzer.discovered_tables = discovered_tables
    analyzer.view_to_tables_map = view_to_tables_map
    analyzer.physical_tables = physical_tables
    result["discovered_tables"] = discovered_tables
    result["view_to_tables_map"] = view_to_tables_map
    result["physical_tables_count"] = len(physical_tables)
    return added


def _apply_hybrid_agent_validation(
    analyzer: DetailedGreenplumFunctionAnalyzer,
    result: Dict[str, Any],
    payload: Dict[str, Any],
) -> None:
    """В гибриде отдаёт предупреждённые фрагменты агенту, если логика не смогла уверенно выделить блоки."""
    if payload.get("analysis_mode") != "hybrid" or not payload.get("use_db_connection"):
        return

    warning_payload = _collect_logic_warning_fragments(analyzer, payload.get("ddl", ""))
    logic_warnings = warning_payload.get("warnings") or []
    if not logic_warnings:
        return

    result["logic_warnings"] = logic_warnings
    result["agent_validated_fragments"] = len(warning_payload.get("fragments") or [])

    print("⚠️ Гибрид: обнаружены предупреждённые фрагменты логики")
    for message in logic_warnings:
        print(f"   • {message}")

    creds = payload.get("agent_credentials") or _agent_credentials()
    if not creds:
        print("⚠️ Гибрид: agent fallback недоступен, ключ GigaChat не задан")
        return

    try:
        from agent.gigachat_agent import get_blocks_and_objects_from_ddl

        fragment_source = "\n\n".join(warning_payload.get("fragments") or []) or payload.get("ddl", "")
        agent_data = get_blocks_and_objects_from_ddl(
            fragment_source,
            credentials_override=creds,
            scope_override=payload.get("agent_scope") or _agent_scope(),
            model_override=_agent_chat_model_from(payload),
        ) or {}
        validated_blocks = agent_data.get("blocks") or []
        replace_logic_blocks = warning_payload.get("executable_count", 0) == 0

        if validated_blocks:
            normalized_existing = set()
            if replace_logic_blocks:
                analyzer.blocks = []
                analyzer.block_types = []
            else:
                normalized_existing = {
                    " ".join(str(block).split()).lower()
                    for block in (getattr(analyzer, "blocks", []) or [])
                    if str(block or "").strip()
                }

            added_blocks = 0
            for block_info in validated_blocks:
                sql = str((block_info or {}).get("sql") or "").strip()
                if not sql:
                    continue
                normalized = " ".join(sql.split()).lower()
                if not replace_logic_blocks and normalized in normalized_existing:
                    continue
                analyzer.blocks.append(sql)
                analyzer.block_types.append(str((block_info or {}).get("type") or "OTHER"))
                normalized_existing.add(normalized)
                added_blocks += 1

            if added_blocks:
                print(f"🤖 Гибрид: агент подтвердил/добавил {added_blocks} логических блоков по предупреждённым фрагментам")
                result["blocks_count"] = len(analyzer.blocks)
                result["block_types"] = analyzer.block_types
                result["use_agent_path"] = True

        merged_objects = _merge_agent_objects_into_discovery(analyzer, result, agent_data.get("objects") or [])
        if merged_objects:
            print(f"🤖 Гибрид: добавлено объектов из агентной валидации: {merged_objects}")
            result["use_agent_path"] = True
            result["objects_referenced_in_blocks"] = max(
                int(result.get("objects_referenced_in_blocks", 0) or 0),
                len(agent_data.get("objects") or []),
            )
    except ImportError as e:
        print(f"⚠️ Гибрид: agent fallback недоступен ({e})")
    except Exception as e:
        print(f"⚠️ Гибрид: ошибка agent fallback для предупреждённых фрагментов: {e}")


def _run_discovery_job(job_id: str, payload: Dict[str, Any]):
    """Запуск первого этапа: обнаружение таблиц"""
    _ensure_event_loop()
    buf = _stream_stdout_to_queue(job_id)
    log_event(
        "job.discovery.worker_started",
        request_id=payload.get("request_id"),
        job_id=job_id,
        stack=payload.get("stack"),
    )
    try:
        with redirect_stdout(buf):
            context = build_discovery_runtime_context(payload, _extract_runtime_analysis_config)
            analysis_mode = context.analysis_mode
            plan_source = context.plan_source
            use_db = context.use_db
            stack = context.stack
            runtime_descriptor = context.runtime_descriptor
            runtime_analysis_config = context.runtime_analysis_config
            analyzer = context.analyzer
            log_runtime_execution_banner(
                stack_label=runtime_descriptor.ui.get('stack_label', stack),
                analysis_mode=analysis_mode,
                plan_source=plan_source,
                use_db=use_db,
                phase='discovery',
                agent_chat_model=_agent_chat_model_from(payload),
                agent_embedding_model=_agent_embedding_model_from(payload),
            )

            if stack != 'greenplum':
                result = analyzer.discover_tables(payload['ddl'])
                result = _apply_runtime_quality_metadata(result, stack=stack, runtime_descriptor=runtime_descriptor, payload=payload)
                result['stack'] = stack
                result['runtime_label'] = runtime_descriptor.ui.get('stack_label', stack)
                result['runtime_config_used'] = runtime_analysis_config
                result['agent_requested_ddl'] = []
                _analysis_orchestrator.set_discovery_result(job_id, analyzer, result)
                log_event(
                    EVENT_JOB_DISCOVERY_COMPLETED,
                    request_id=payload.get("request_id"),
                    job_id=job_id,
                    stack=stack,
                    discovered_objects=len(result.get("discovered_tables", {}) or {}),
                )
                return

            # Чистый агентский режим (гибрид + без БД): блоки и объекты ищет только агент, парсер не вызываем.
            # При ошибке агента — не возвращаемся к логике (парсеру), завершаем с ошибкой.
            # К калькуляции возвращаемся только когда план от агента содержит все множители — без проверки БД.
            is_pure_agent = not use_db and payload.get('analysis_mode') == 'hybrid'
            if is_pure_agent:
                # Кэш: при неизменном DDL переиспользуем результат предыдущего успешного прогона агента
                ddl_hash = hashlib.sha256((payload.get('ddl') or "").encode("utf-8")).hexdigest()
                desc_hash = hashlib.sha256((payload.get('agent_description') or "").encode("utf-8")).hexdigest()
                try:
                    from agent.agent_cache_db import get_state, set_state, state_key_discovery
                    state_key = state_key_discovery(ddl_hash, use_db, desc_hash)
                    cached = get_state(state_key)
                    if cached and cached.get("use_agent_path") and cached.get("discovered_tables") and cached.get("blocks"):
                        analyzer.blocks = cached["blocks"]
                        analyzer.block_types = cached["block_types"]
                        analyzer.input_type = cached.get("input_type", "function")
                        analyzer.discovered_tables = cached["discovered_tables"]
                        analyzer.view_to_tables_map = cached.get("view_to_tables_map") or {}
                        analyzer.variables = cached.get("variables") or {}
                        analyzer.function_params = cached.get("function_params") or []
                        analyzer.func_name = cached.get("function", "unknown")
                        analyzer.temp_tables = set(cached.get("temp_tables") or [])
                        analyzer.physical_tables = set(tuple(p) for p in (cached.get("physical_tables") or []))
                        result = {k: cached[k] for k in (
                            "input_type", "function", "blocks_count", "block_types", "temp_tables",
                            "discovered_tables", "view_to_tables_map", "physical_tables_count",
                            "objects_referenced_in_blocks", "variables", "status"
                        ) if k in cached}
                        result["agent_requested_ddl"] = cached.get("agent_requested_ddl") or []
                        result["use_agent_path"] = True
                        print("📦 [Чистый агент] Использован кэш (блоки и объекты от агента)")
                        _analysis_orchestrator.set_discovery_result(job_id, analyzer, result)
                        log_event(
                            EVENT_JOB_DISCOVERY_COMPLETED,
                            request_id=payload.get("request_id"),
                            job_id=job_id,
                            stack=stack,
                            discovered_objects=len(result.get("discovered_tables", {}) or {}),
                            source="cache",
                        )
                        return
                except Exception:
                    pass

                creds = payload.get('agent_credentials') or _agent_credentials()
                if creds:
                    try:
                        from agent.gigachat_agent import get_blocks_and_objects_from_ddl
                        agent_data = get_blocks_and_objects_from_ddl(
                            payload['ddl'],
                            credentials_override=creds,
                            scope_override=payload.get('agent_scope') or _agent_scope(),
                            model_override=_agent_chat_model_from(payload),
                        )
                        if agent_data and (agent_data.get("blocks") or agent_data.get("objects")):
                            blocks_list = agent_data.get("blocks") or []
                            objects_list = agent_data.get("objects") or []
                            function_params_list = agent_data.get("function_params") or []
                            variables_list = agent_data.get("variables") or []
                            analyzer.blocks = [b.get("sql", "") for b in blocks_list if b.get("sql")]
                            analyzer.block_types = [b.get("type", "OTHER") for b in blocks_list if b.get("sql")]
                            analyzer.input_type = 'function'
                            analyzer.func_name = "unknown"
                            analyzer.function_params = [str(p) for p in function_params_list if p]
                            analyzer.variables = {str(v): "" for v in variables_list if v}
                            analyzer.view_to_tables_map = {}
                            analyzer.temp_tables = {t for t in objects_list if isinstance(t, str) and "." not in t.strip()}
                            analyzer.physical_tables = set()
                            agent_tables = {}
                            for full_name in objects_list:
                                full_name = str(full_name).strip()
                                if not full_name:
                                    continue
                                if "." in full_name:
                                    parts = full_name.split(".", 1)
                                    schema, table = parts[0].strip(), parts[1].strip()
                                else:
                                    schema, table = "public", full_name
                                agent_tables[full_name] = {
                                    'schema': schema, 'table': table, 'current_rows': 0, 'size_gb': 0.0,
                                    'avg_row_size_bytes': 0, 'columns': 0, 'user_rows': 0,
                                }
                            analyzer.discovered_tables = agent_tables
                            result = {
                                'input_type': 'function', 'function': analyzer.func_name,
                                'blocks_count': len(analyzer.blocks), 'block_types': analyzer.block_types,
                                'temp_tables': list(analyzer.temp_tables), 'discovered_tables': agent_tables, 'view_to_tables_map': {},
                                'physical_tables_count': len(objects_list), 'objects_referenced_in_blocks': len(objects_list),
                                'variables': analyzer.variables, 'function_params': analyzer.function_params,
                                'status': 'tables_discovered', 'agent_requested_ddl': [],
                                'use_agent_path': True,
                            }
                            print("🤖 [Агент] Чистый агентский режим: блоки и объекты найдены агентом")
                            print(f"   Итого: блоков {len(analyzer.blocks)}, объектов {len(objects_list)}, параметров {len(analyzer.function_params)}, переменных {len(analyzer.variables)}")
                            _analysis_orchestrator.set_discovery_result(job_id, analyzer, result)
                            log_event(
                                EVENT_JOB_DISCOVERY_COMPLETED,
                                request_id=payload.get("request_id"),
                                job_id=job_id,
                                stack=stack,
                                discovered_objects=len(agent_tables),
                                source="pure_agent",
                            )
                            try:
                                from agent.agent_cache_db import set_state, state_key_discovery
                                ddl_h = hashlib.sha256((payload.get('ddl') or "").encode("utf-8")).hexdigest()
                                desc_h = hashlib.sha256((payload.get('agent_description') or "").encode("utf-8")).hexdigest()
                                state_key = state_key_discovery(ddl_h, use_db, desc_h)
                                state_to_save = dict(result)
                                state_to_save["blocks"] = analyzer.blocks
                                state_to_save["view_to_tables_map"] = {}
                                state_to_save["variables"] = analyzer.variables
                                state_to_save["function_params"] = analyzer.function_params
                                state_to_save["function"] = analyzer.func_name
                                state_to_save["temp_tables"] = []
                                state_to_save["physical_tables"] = []
                                state_to_save["input_type"] = "function"
                                set_state(state_key, state_to_save)
                            except Exception:
                                pass
                            return
                        else:
                            print("⚠️ Чистый агентский режим: агент вернул пустой результат (нет блоков и объектов)")
                    except ImportError as e:
                        if "gigachat" in str(e).lower():
                            print("⚠️ Чистый агентский режим: не установлен пакет gigachat. Выполните: pip install gigachat")
                        else:
                            print(f"⚠️ Чистый агентский режим: {e}")
                    except Exception as e:
                        print(f"⚠️ Чистый агентский режим (блоки и объекты): {e}")
                else:
                    print("⚠️ Чистый агентский режим: ключ GigaChat не задан (введите в форме «Ввести ключ» или задайте в .env)")

                # Чистый агент: при любой ошибке или пустом результате — не переходим на парсер, завершаем с ошибкой
                _analysis_orchestrator.fail_job(
                    job_id,
                    'Чистый агентский режим: не удалось получить блоки и объекты от агента. '
                    'Проверьте ключ GigaChat, установите gigachat (pip install gigachat) и повторите. '
                    'Парсер не используется — только агент.'
                )
                return

            # Проверка кэша состояний: при неизменном DDL и текстовом описании переиспользуем результат (экономия токенов)
            ddl_hash = hashlib.sha256((payload.get('ddl') or "").encode("utf-8")).hexdigest()
            desc_hash = hashlib.sha256((payload.get('agent_description') or "").encode("utf-8")).hexdigest()
            try:
                from agent.agent_cache_db import get_state, set_state, state_key_discovery
                state_key = state_key_discovery(ddl_hash, use_db, desc_hash)
                cached = get_state(state_key)
                # В чистом агентском режиме не используем кэш с пустыми таблицами
                if is_pure_agent and cached:
                    if not cached.get("discovered_tables") or len(cached.get("discovered_tables") or {}) == 0:
                        cached = None
                if cached and cached.get("discovered_tables") is not None and cached.get("blocks") is not None:
                    # Восстановление анализатора из кэша
                    analyzer.blocks = cached["blocks"]
                    analyzer.block_types = cached["block_types"]
                    analyzer.input_type = cached.get("input_type") or (
                        "function" if cached.get("use_agent_path") else None
                    )
                    analyzer.discovered_tables = cached["discovered_tables"]
                    analyzer.view_to_tables_map = cached.get("view_to_tables_map") or {}
                    analyzer.variables = cached.get("variables") or {}
                    analyzer.function_params = cached.get("function_params") or []
                    analyzer.func_name = cached.get("function", "unknown")
                    analyzer.temp_tables = set(cached.get("temp_tables") or [])
                    analyzer.physical_tables = set(tuple(p) for p in (cached.get("physical_tables") or []))
                    result = {k: cached[k] for k in (
                        "input_type", "function", "blocks_count", "block_types", "temp_tables",
                        "discovered_tables", "view_to_tables_map", "physical_tables_count",
                        "objects_referenced_in_blocks", "variables", "status"
                    ) if k in cached}
                    result["agent_requested_ddl"] = cached.get("agent_requested_ddl") or []
                    result["use_agent_path"] = cached.get("use_agent_path", False)
                    if use_db:
                        conn = _build_conn_string(
                            payload.get('stand_type', 'PROM'),
                            payload['user'], payload['password'],
                            payload.get('host'), payload.get('port'), payload.get('dbname')
                        )
                        analyzer.connect(conn)
                    print("📦 Использован кэш состояний (discovery без повторного расчёта)")
                    _analysis_orchestrator.set_discovery_result(job_id, analyzer, result)
                    return
            except Exception:
                pass

            # Подключаемся к БД если нужно
            if use_db:
                conn = _build_conn_string(
                    payload.get('stand_type', 'PROM'),
                    payload['user'], payload['password'],
                    payload.get('host'), payload.get('port'), payload.get('dbname')
                )
                if not analyzer.connect(conn):
                    _analysis_orchestrator.fail_job(job_id, 'Не удалось подключиться к БД. Проверьте логин и пароль.')
                    return

            # Запускаем обнаружение таблиц
            result = analyzer.discover_tables(payload['ddl'])
            result = _apply_runtime_quality_metadata(result, stack=stack, runtime_descriptor=runtime_descriptor, payload=payload)

            # В гибриде предупреждённые логикой фрагменты дополнительно валидирует агент.
            _apply_hybrid_agent_validation(analyzer, result, payload)
            
            # Чистый агентский режим: без БД + гибрид — объекты извлекает агент
            if not use_db and payload.get('analysis_mode') == 'hybrid':
                creds = payload.get('agent_credentials') or _agent_credentials()
                if creds:
                    try:
                        from agent.gigachat_agent import get_objects_from_sql_or_function
                        obj_list = get_objects_from_sql_or_function(
                            payload['ddl'],
                            credentials_override=creds,
                            scope_override=payload.get('agent_scope') or _agent_scope(),
                            model_override=_agent_chat_model_from(payload),
                        )
                        if obj_list:
                            print(f"🤖 [Агент] Гибрид (без БД): объекты найдены — {len(obj_list)} шт.: {', '.join(obj_list[:5])}{'…' if len(obj_list) > 5 else ''}")
                            agent_tables = {}
                            for full_name in obj_list:
                                full_name = str(full_name).strip()
                                if not full_name:
                                    continue
                                if "." in full_name:
                                    parts = full_name.split(".", 1)
                                    schema, table = parts[0].strip(), parts[1].strip()
                                else:
                                    schema, table = "public", full_name
                                agent_tables[full_name] = {
                                    'schema': schema,
                                    'table': table,
                                    'current_rows': 0,
                                    'size_gb': 0.0,
                                    'avg_row_size_bytes': 0,
                                    'columns': 0,
                                    'user_rows': 0,
                                }
                            result['discovered_tables'] = agent_tables
                            result['status'] = 'tables_discovered'
                            result['use_agent_path'] = True
                            analyzer.discovered_tables = agent_tables
                            result['agent_requested_ddl'] = []
                    except ImportError as e:
                        if "gigachat" in str(e).lower():
                            print("⚠️ Чистый агентский режим: не установлен пакет gigachat. Выполните: pip install gigachat")
                        else:
                            print(f"⚠️ Чистый агентский режим (извлечение объектов): {e}")
                    except Exception as e:
                        print(f"⚠️ Чистый агентский режим (извлечение объектов): {e}")
                else:
                    print("⚠️ Чистый агентский режим: ключ GigaChat не задан (введите в форме «Ввести ключ» или задайте в .env)")
            
            # В гибридном режиме: агент сверяет найденные объекты с текстом и запрашивает DDL по недостающим
            if payload.get('analysis_mode') == 'hybrid':
                try:
                    from agent.gigachat_agent import get_missing_objects_for_ddl
                    found_objects = list(result.get('discovered_tables', {}).keys())
                    creds = payload.get('agent_credentials') or _agent_credentials()
                    if creds:
                        missing = get_missing_objects_for_ddl(
                            payload['ddl'],
                            found_objects,
                            credentials_override=creds,
                            scope_override=payload.get('agent_scope') or _agent_scope(),
                            model_override=_agent_chat_model_from(payload),
                        )
                        result['agent_requested_ddl'] = missing
                        if missing:
                            print(f"📋 [Агент] Гибрид: запрос DDL для недостающих объектов: {missing}")
                    else:
                        result['agent_requested_ddl'] = []
                    ref_in_blocks = result.get('objects_referenced_in_blocks', 0)
                    discovered_count = len(result.get('discovered_tables', {}))
                    if discovered_count == 0 or (ref_in_blocks > 0 and discovered_count < ref_in_blocks):
                        result['use_agent_path'] = True
                        print(f"📋 [Агент] Гибрид: включён агентский путь (объектов {discovered_count}, ссылок в блоках {ref_in_blocks})")
                except ImportError as e:
                    result['agent_requested_ddl'] = []
                    if "gigachat" in str(e).lower():
                        print("⚠️ Гибрид: не установлен пакет gigachat. Выполните: pip install gigachat")
                    else:
                        print(f"⚠️ Проверка недостающих объектов агентом: {e}")
                except Exception as e:
                    result['agent_requested_ddl'] = []
                    print(f"⚠️ Проверка недостающих объектов агентом: {e}")
            else:
                result['agent_requested_ddl'] = []
            
            # Сохраняем анализатор и результат
            _analysis_orchestrator.set_discovery_result(job_id, analyzer, result)
            log_event(
                EVENT_JOB_DISCOVERY_COMPLETED,
                request_id=payload.get("request_id"),
                job_id=job_id,
                stack=stack,
                discovered_objects=len(result.get("discovered_tables", {}) or {}),
            )

            # Кэш состояний для переиспользования при следующем discovery без изменений
            # В чистом агентском режиме не кэшируем результат с пустыми таблицами
            try:
                from agent.agent_cache_db import set_state, state_key_discovery
                if not use_db and payload.get('analysis_mode') == 'hybrid' and len(result.get("discovered_tables") or {}) == 0:
                    pass  # не сохраняем неудачный чистый агентский прогон
                else:
                    state_key = state_key_discovery(ddl_hash, use_db, desc_hash)
                    state_to_save = dict(result)
                    state_to_save["blocks"] = getattr(analyzer, "blocks", [])
                    state_to_save["view_to_tables_map"] = getattr(analyzer, "view_to_tables_map", {})
                    state_to_save["variables"] = getattr(analyzer, "variables", {})
                    state_to_save["function_params"] = getattr(analyzer, "function_params", [])
                    state_to_save["function"] = getattr(analyzer, "func_name", "unknown")
                    state_to_save["temp_tables"] = list(getattr(analyzer, "temp_tables", []))
                    state_to_save["physical_tables"] = [list(p) for p in getattr(analyzer, "physical_tables", set())]
                    set_state(state_key, state_to_save)
            except Exception:
                pass
    except Exception as e:
        err_safe = _mask_secret(str(e))
        _analysis_orchestrator.fail_job(job_id, err_safe)
        _enqueue_log(job_id, f"\n❌ Ошибка: {err_safe}\n")
        log_event(
            "job.discovery.failed",
            request_id=payload.get("request_id"),
            job_id=job_id,
            stack=payload.get("stack"),
            error=err_safe,
        )
    finally:
        _enqueue_log(job_id, "\n[STREAM_END]\n")


def _run_analysis_job(job_id: str, payload: Dict[str, Any]):
    """Запуск второго этапа: анализ с пользовательскими размерами"""
    _ensure_event_loop()
    buf = _stream_stdout_to_queue(job_id)
    job = None
    try:
        with redirect_stdout(buf):
            job = _analysis_orchestrator.require_job(job_id)
            log_event(
                "job.analysis.worker_started",
                request_id=job.get("request_id"),
                job_id=job_id,
                stack=job.get("stack"),
            )
            context = build_analysis_runtime_context(
                job,
                credentials_resolver=_agent_credentials,
                scope_resolver=_agent_scope,
            )
            analysis_mode = context.analysis_mode
            plan_source = context.plan_source
            use_db = context.use_db
            stack = context.stack
            runtime_descriptor = context.runtime_descriptor
            analyzer = context.analyzer
            agent_credentials = context.agent_credentials
            agent_scope = context.agent_scope
            log_runtime_execution_banner(
                stack_label=runtime_descriptor.ui.get('stack_label', stack),
                analysis_mode=analysis_mode,
                plan_source=plan_source,
                use_db=use_db,
                phase='analysis',
                agent_chat_model=_agent_chat_model_from(job),
                agent_embedding_model=_agent_embedding_model_from(job),
            )

            # Запускаем анализ с пользовательскими размерами (режим и источник плана передаём в анализатор)
            params = payload.get('params', [])
            
            # Если параметры не переданы, пробуем взять из сохраненных
            if not params and 'saved_params' in job:
                params = job['saved_params']
                print(f"🔄 Использованы сохраненные параметры из saved_params: {params}")
            elif not params and 'discovery_result' in job:
                # Пробуем взять из discovery_result если есть
                discovery = job['discovery_result']
                params = discovery.get('user_params', [])
                print(f"🔄 Использованы параметры из discovery: {params}")
            
            user_sizes = payload.get('user_sizes', {})
            
            print(f"🔍 Запуск анализа с параметрами: {params}")
            print(f"📊 Размеры таблиц: {len(user_sizes)} шт.")
            
            result = analyzer.analyze_with_user_sizes(
                params,
                user_sizes,
                analysis_mode=analysis_mode,
                plan_source=plan_source,
                agent_credentials=agent_credentials,
                agent_scope=agent_scope,
                agent_chat_model=_agent_chat_model_from(job),
                agent_embedding_model=_agent_embedding_model_from(job),
            )
            result = _apply_runtime_quality_metadata(result, stack=stack, runtime_descriptor=runtime_descriptor, payload=job)
            result['stack'] = stack
            result['runtime_label'] = runtime_descriptor.ui.get('stack_label', stack)
            if isinstance(result, dict):
                result["agent_chat_model"] = _agent_chat_model_from(job)
                result["agent_embedding_model"] = _agent_embedding_model_from(job)
            _analysis_orchestrator.complete_analysis(job_id, result)
            log_event(
                "job.analysis.completed",
                request_id=job.get("request_id"),
                job_id=job_id,
                stack=stack,
                risk=result.get("risk"),
                analyzed_blocks=result.get("analyzed_blocks"),
            )
    except Exception as e:
        err_safe = _mask_secret(str(e))
        _analysis_orchestrator.fail_job(job_id, err_safe)
        _enqueue_log(job_id, f"\n❌ Ошибка: {err_safe}\n")
        log_event(
            "job.analysis.failed",
            request_id=(job or {}).get("request_id") if isinstance(job, dict) else payload.get("request_id"),
            job_id=job_id,
            error=err_safe,
        )
        import traceback
        traceback.print_exc()
    finally:
        _enqueue_log(job_id, "\n[STREAM_END]\n")


@app.route('/')
@app.route('/detailed')
def detailed_index():
    """Страница ввода DDL"""
    error = request.args.get('error', '')
    stand_hosts = {k: v.get('host') for k, v in STANDS.items() if v.get('host')}
    return render_template('detailed_input.html', stands=STANDS, stand_hosts=stand_hosts, error=error)


@app.route('/detailed/discover', methods=['POST'])
def detailed_discover():
    """Запуск первого этапа - обнаружение таблиц"""
    # Получаем данные формы
    ddl = request.form.get('ddl')
    stack = normalize_stack(request.form.get('stack'))
    pure_agent_mode = request.form.get('pure_agent_mode') == '1' or request.form.get('pure_agent') == 'on'
    use_db = False if pure_agent_mode else (request.form.get('use_db_connection') == 'on')

    # Режим анализа: logic | hybrid. use_hybrid — checkbox; pure_agent_mode — скрытый input (чистый агент)
    use_hybrid = request.form.get('use_hybrid') == 'on'
    analysis_mode = 'hybrid' if (use_hybrid or pure_agent_mode) else 'logic'
    plan_source = 'agent' if analysis_mode == 'hybrid' else 'db'

    # При гибриде/чистом агенте нужен ключ API
    if analysis_mode == 'hybrid':
        form_creds_raw = (request.form.get('agent_credentials') or '').strip()
        creds = _agent_credentials(form_creds_raw) if form_creds_raw else _agent_credentials()
        if not creds:
            return redirect(url_for('detailed_index', error='agent_key_required'))

    # Базовые настройки (ключ агента передаём в поток — в потоке нет доступа к сессии)
    # agent_description участвует в ключе кэша: при смене описания не переиспользуем старый результат
    agent_description = (request.form.get('agent_description') or '').strip()
    form_creds = (request.form.get('agent_credentials') or '').strip()
    form_scope = (request.form.get('agent_scope') or '').strip()
    form_chat_model = (request.form.get('agent_chat_model') or '').strip()
    form_emb_model = (request.form.get('agent_embedding_model') or '').strip()
    data = {
        'stack': stack,
        'ddl': ddl,
        'agent_description': agent_description,
        'use_db_connection': use_db,
        'segments': int(request.form.get('segments', 120)),
        'ram_per_seg_gb': float(request.form.get('ram_per_seg_gb', 153.6)),
        'analysis_mode': analysis_mode,
        'plan_source': plan_source,
        'agent_credentials': _agent_credentials(form_creds),
        'agent_scope': _agent_scope(form_scope),
        'agent_chat_model': form_chat_model or None,
        'agent_embedding_model': form_emb_model or None,
    }

    if stack == 'spark':
        data.update({
            'catalog': (request.form.get('catalog') or '').strip() or None,
            'namespace': (request.form.get('namespace') or '').strip() or None,
            'executor_instances': request.form.get('executor_instances') or 4,
            'executor_cores': request.form.get('executor_cores') or 4,
            'executor_memory': (request.form.get('executor_memory') or '').strip() or '8g',
            'spark_metadata_json': (request.form.get('spark_metadata_json') or '').strip() or None,
            'spark_profile_json': (request.form.get('spark_profile_json') or '').strip() or None,
        })
    elif stack == 'pyspark':
        data.update({
            'session_name': (request.form.get('pyspark_session_name') or request.form.get('session_name') or '').strip() or None,
            'pyspark_executor_instances': request.form.get('pyspark_executor_instances') or 4,
            'pyspark_executor_memory': (request.form.get('pyspark_executor_memory') or '').strip() or '8g',
            'pyspark_metadata_json': (request.form.get('pyspark_metadata_json') or '').strip() or None,
            'pyspark_profile_json': (request.form.get('pyspark_profile_json') or '').strip() or None,
        })
    
    # Проверяем наличие DDL
    if not ddl or not ddl.strip():
        return redirect(url_for('detailed_index', error='ddl_required'))
    
    # Если используем БД, добавляем параметры подключения
    if use_db:
        if stack == 'greenplum':
            user = request.form.get('user', '').strip()
            password = request.form.get('password', '').strip()
            if not user or not password:
                return redirect(url_for('detailed_index', error='db_required'))
            data.update({
                'stand_type': request.form.get('stand_type', 'PROM'),
                'host': request.form.get('host') or None,
                'port': request.form.get('port') or None,
                'dbname': request.form.get('dbname') or None,
                'user': user,
                'password': password,
            })
        elif stack == 'spark':
            master_url = (request.form.get('master_url') or '').strip()
            if not master_url:
                return redirect(url_for('detailed_index', error='db_required'))
            data.update({
                'master_url': master_url,
                'spark_user': (request.form.get('spark_user') or '').strip() or None,
                'spark_password': (request.form.get('spark_password') or '').strip() or None,
            })
        else:
            master_url = (request.form.get('pyspark_master_url') or '').strip()
            if not master_url:
                return redirect(url_for('detailed_index', error='db_required'))
            data.update({
                'master_url': master_url,
                'pyspark_user': (request.form.get('pyspark_user') or '').strip() or None,
                'pyspark_password': (request.form.get('pyspark_password') or '').strip() or None,
            })
    
    # Создаём задачу (сохраняем режим и источник плана для этапа анализа)
    job_id = datetime.now().strftime('%Y%m%d%H%M%S%f') + '_disc'
    _analysis_orchestrator.create_discovery_job(job_id, {
        'status': JOB_STATUS_RUNNING,
        'stack': stack,
        'execution_backend': settings.job_runner_backend,
        'request_id': getattr(g, 'request_id', None),
        'discovery_result': None,
        'analysis_mode': analysis_mode,
        'plan_source': plan_source,
        'use_db_connection': use_db,
        'agent_credentials': data['agent_credentials'],
        'agent_scope': data['agent_scope'],
        'agent_chat_model': data.get('agent_chat_model'),
        'agent_embedding_model': data.get('agent_embedding_model'),
        'segments': data.get('segments'),
        'ram_per_seg_gb': data.get('ram_per_seg_gb'),
        'master_url': data.get('master_url'),
        'catalog': data.get('catalog'),
        'namespace': data.get('namespace'),
        'session_name': data.get('session_name'),
        'executor_instances': data.get('executor_instances'),
        'executor_cores': data.get('executor_cores'),
        'executor_memory': data.get('executor_memory'),
        'pyspark_executor_instances': data.get('pyspark_executor_instances'),
        'pyspark_executor_memory': data.get('pyspark_executor_memory'),
        'spark_metadata_json': data.get('spark_metadata_json'),
        'spark_profile_json': data.get('spark_profile_json'),
        'pyspark_metadata_json': data.get('pyspark_metadata_json'),
        'pyspark_profile_json': data.get('pyspark_profile_json'),
    })
    log_event(
        "job.discovery.created",
        request_id=getattr(g, "request_id", None),
        job_id=job_id,
        stack=stack,
        analysis_mode=analysis_mode,
        use_db_connection=use_db,
    )
    
    # Запускаем в отдельном потоке
    run_handle = _job_runner.start(_run_discovery_job, job_id, data)
    _job_service.update_job(
        job_id,
        execution_backend=run_handle.backend,
        execution_run_id=run_handle.run_id,
    )
    log_event(
        "job.discovery.enqueued",
        request_id=getattr(g, "request_id", None),
        job_id=job_id,
        backend=run_handle.backend,
        execution_run_id=run_handle.run_id,
    )
    
    return redirect(url_for('discovery_result', job_id=job_id))


@app.route('/discovery/result/<job_id>')
def discovery_result(job_id: str):
    """Страница с результатами обнаружения таблиц"""
    job = _job_service.get_job(job_id)
    if not job:
        return JOB_NOT_FOUND_MESSAGE, 404
    mode = job.get('analysis_mode', 'logic')
    use_db = job.get('use_db_connection', True)
    loader_mode = _effective_loader_mode(mode, use_db)
    return render_template(
        'table_sizes.html',
        job_id=job_id,
        status=job['status'],
        loader_mode=loader_mode,
        stack=job.get('stack', 'greenplum'),
        agent_chat_model=job.get('agent_chat_model') or '',
        agent_embedding_model=job.get('agent_embedding_model') or '',
    )


@app.route('/detailed/analyze', methods=['POST'])
def detailed_analyze():
    """Запуск второго этапа - анализ с пользовательскими размерами"""
    job_id = request.form.get('job_id')
    
    # Проверяем существование задачи
    job = _job_service.get_job(job_id)
    if not job:
        return api_error("job_not_found", JOB_NOT_FOUND_MESSAGE, http_status=404)
    
    # Получаем параметры функции из формы
    params_str = request.form.get('params', '').strip()
    params = [p.strip() for p in params_str.split(',') if p.strip()] if params_str else []
    
    print(f"DEBUG: Получены параметры для анализа из формы: {params}")
    
    # СОХРАНЯЕМ параметры в задаче для последующих запусков
    _analysis_orchestrator.store_analysis_params(job_id, params)
    if job.get('discovery_result'):
        print(f"Сохранены параметры в discovery_result: {params}")
    
    # Очищаем старые данные перед новым запуском
    analyzer = job.get('analyzer')
    if not analyzer:
        return redirect(url_for('detailed_index', error='job_restore_requires_restart'))
    if analyzer:
        analyzer.reset_for_rerun()
        print(f"🔄 Состояние анализатора сброшено для job_id: {job_id}")
    
    # Обновляем статус; сохраняем ключ из задачи (discovery) или .env — не перезаписываем UI-ключ
    _analysis_orchestrator.prepare_analysis_run(job_id, _agent_credentials, _agent_scope)
    
    # Получаем пользовательские размеры из формы
    # Ключи могут быть с ___DOT___ вместо точки (для совместимости)
    user_sizes = {}
    for key in request.form:
        if key.startswith('size_'):
            raw_name = key[5:]  # убираем префикс 'size_'
            table_name = raw_name.replace('___DOT___', '.')
            try:
                val_str = request.form.get(key, '').strip()
                value = int(val_str) if val_str else 0
                if value >= 0:
                    user_sizes[table_name] = value
            except ValueError:
                pass
    
    print(f"DEBUG: Получены пользовательские размеры: {len(user_sizes)} таблиц")
    if user_sizes:
        for t, v in list(user_sizes.items())[:10]:
            print(f"  {t}: {v:,} строк")
        if len(user_sizes) > 10:
            print(f"  ... и ещё {len(user_sizes) - 10}")
    
    # Запускаем мониторинг производительности
    _analysis_orchestrator.start_performance_monitor(job_id)
    log_event(
        "job.analysis.started",
        request_id=job.get("request_id"),
        job_id=job_id,
        params_count=len(params),
        user_sizes_count=len(user_sizes),
    )
    
    # Запускаем анализ в отдельном потоке
    run_handle = _job_runner.start(_run_analysis_job, job_id, {
        'params': params,
        'user_sizes': user_sizes
    })
    _job_service.update_job(
        job_id,
        execution_backend=run_handle.backend,
        execution_run_id=run_handle.run_id,
    )
    log_event(
        "job.analysis.enqueued",
        request_id=job.get("request_id"),
        job_id=job_id,
        backend=run_handle.backend,
        execution_run_id=run_handle.run_id,
    )
    
    # Передаём режим в URL, чтобы при 404 (перезапуск сервера) лоадер показывал правильную иконку
    job = _job_service.require_job(job_id)
    mode = job.get('analysis_mode', 'logic')
    use_db = job.get('use_db_connection', True)
    loader_mode = _effective_loader_mode(mode, use_db)
    return redirect(url_for('detailed_result', job_id=job_id) + f'?mode={loader_mode}')


@app.route('/detailed/result/<job_id>')
def detailed_result(job_id: str):
    """Страница с результатами анализа"""
    job = _job_service.get_job(job_id)
    if not job:
        return JOB_NOT_FOUND_MESSAGE, 404
    # Режим из URL (при редиректе) или из job
    mode = request.args.get('mode')
    if not mode:
        m = job.get('analysis_mode', 'logic')
        use_db = job.get('use_db_connection', True)
        mode = _effective_loader_mode(m, use_db)
    return render_template(
        'detailed_result.html',
        job_id=job_id,
        status=job['status'],
        loader_mode=mode,
        stack=job.get('stack', 'greenplum'),
        agent_chat_model=job.get('agent_chat_model') or '',
        agent_embedding_model=job.get('agent_embedding_model') or '',
    )


@app.route('/stream/<job_id>')
def stream(job_id: str):
    """Server-Sent Events поток логов"""
    if not _job_service.has_log_queue(job_id) and not _job_service.get_job(job_id):
        return "Лог не найден", 404

    def event_stream():
        job = _job_service.get_job(job_id) or {}
        execution_backend = job.get('execution_backend') or settings.job_runner_backend
        q = _job_service.get_log_queue(job_id)
        if q is not None and execution_backend == 'thread':
            while True:
                line = q.get()
                yield f"data: {line}\n\n"
                if line.strip() == '[STREAM_END]':
                    break
            return

        sent_lines = 0
        while True:
            lines = _job_service.read_persisted_logs(job_id)
            while sent_lines < len(lines):
                line = lines[sent_lines]
                sent_lines += 1
                yield f"data: {line}\n\n"
                if line.strip() == '[STREAM_END]':
                    return
            current_job = _job_service.get_job(job_id)
            if current_job and current_job.get('status') in (JOB_STATUS_DONE, JOB_STATUS_ERROR):
                yield "data: [STREAM_END]\n\n"
                return
            time.sleep(0.5)

    return Response(event_stream(), mimetype='text/event-stream')


@app.route('/status/<job_id>')
def status(job_id: str):
    """Возвращает статус задачи"""
    job = _job_service.get_job(job_id)
    if not job:
        return api_error("job_not_found", JOB_NOT_FOUND_MESSAGE, http_status=404, job_status=JOB_STATUS_NOT_FOUND)
    
    st = job['status']
    res = {'status': st}
    res['request_id'] = job.get('request_id')
    res['stack'] = job.get('stack', 'greenplum')
    res['analysis_mode'] = job.get('analysis_mode', 'logic')
    res['use_db_connection'] = job.get('use_db_connection', False)
    res['agent_chat_model'] = job.get('agent_chat_model') or ''
    res['agent_embedding_model'] = job.get('agent_embedding_model') or ''
    res['execution_backend'] = job.get('execution_backend')
    res['execution_run_id'] = job.get('execution_run_id')
    if 'discovery_result' in job and job['discovery_result']:
        res['use_agent_path'] = job['discovery_result'].get('use_agent_path', False)
    
    # Для этапа обнаружения таблиц
    if st == JOB_STATUS_TABLES_DISCOVERED and job.get('discovery_result'):
        res['discovery'] = job['discovery_result']
    
    # Для завершённого анализа
    if st == JOB_STATUS_DONE and job.get('result'):
        jr = job['result']
        fn = jr.get('function')
        in_type = jr.get('input_type')
        fn_l = str(fn or '').strip().lower()
        if not fn_l or fn_l in ('unknown', 'n/a', 'na'):
            fn = 'SQL-запрос' if in_type == 'query' else '—'
        res['summary'] = {
            'function': fn,
            'input_type': in_type,
            'blocks_analyzed': jr.get('analyzed_blocks', 0),
            'total_memory_gb': jr.get('total_memory_gb', 0),
            'antipattern_added_gb': jr.get('antipattern_added_gb', 0),
            'estimated_time_sec': jr.get('estimated_time_sec', 0),
            'risk': jr.get('risk', 'N/A'),
        }
    
    # Если есть ошибка
    if job.get('error'):
        res['error'] = job['error']
    
    return api_ok(data=res, **res)


@app.route('/details/<job_id>')
def details(job_id: str):
    """Возвращает полные результаты анализа в JSON"""
    job = _job_service.get_job(job_id)
    if not job or job['status'] != JOB_STATUS_DONE:
        return api_error("result_unavailable", "Результат недоступен", http_status=400)
    out = dict(job['result'])
    out['request_id'] = job.get('request_id')
    out['stack'] = job.get('stack', 'greenplum')
    out['analysis_mode'] = job.get('analysis_mode', 'logic')
    out['use_db_connection'] = job.get('use_db_connection', False)
    return api_ok(data=out, **out)


@app.route('/performance/<job_id>')
def get_performance(job_id: str):
    """Возвращает статистику производительности"""
    monitor = _performance_monitors.get(job_id)
    if not monitor:
        return api_error("performance_monitor_not_found", "Монитор не найден", http_status=404)
    stats = monitor.get_stats()
    return api_ok(data=stats, **stats)


if __name__ == '__main__':
    app.run(host=settings.flask_host, port=settings.flask_port, debug=settings.flask_debug)