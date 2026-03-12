#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import io
import json
import os
import threading
import queue
from contextlib import redirect_stdout
from datetime import datetime
from typing import Dict, Any, List, Optional

# Пути: app_gpa (webapp) и корень проекта
_webapp_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_webapp_dir)

# Загрузка .env для GIGACHAT_CREDENTIALS, GIGACHAT_VERIFY_SSL_CERTS и др.
try:
    from dotenv import load_dotenv
    for _d in (_project_root, _webapp_dir):
        _env = os.path.join(_d, ".env")
        if os.path.isfile(_env):
            load_dotenv(_env)
            break
    else:
        load_dotenv()
except ImportError:
    pass

# Базовое состояние зашито в ядре — при старте применяем baseline (из файла или из ядра)
try:
    from agent.agent_cache_db import restore_baseline_config
    restore_baseline_config()
except Exception:
    pass

from flask import Flask, render_template, request, redirect, url_for, Response, jsonify, session, send_file
from jinja2 import ChoiceLoader, FileSystemLoader

from detailed.detailed_analyzer import DetailedGreenplumFunctionAnalyzer, ClusterConfig
from detailed.performance_monitor import PerformanceMonitor

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-this-in-production'

# Добавляем пути для шаблонов
app.jinja_loader = ChoiceLoader([
    FileSystemLoader('templates'),
    FileSystemLoader('detailed/templates')
])

# Информация об приложении для модального окна «О приложении»
@app.context_processor
def inject_app_info():
    return {
        'app_name': 'GPA Analyzer',
        'app_author': 'Dmitry Solonnikov',
        'app_version': '1.0',
        'app_description': 'Оценка нагрузки и рисков выполнения PL/pgSQL-функций в Greenplum по планам запросов.',
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
    for _d in (_project_root, _webapp_dir):
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


@app.route('/api/agent/env-token-status', methods=['GET'])
def api_agent_env_token_status():
    """Проверка наличия токена в .key или .env (без раскрытия значения)."""
    creds = _agent_credentials()
    return jsonify({"hasToken": bool(creds)})


@app.route('/api/agent/validate-env', methods=['POST'])
def api_agent_validate_env():
    """Проверка валидности токена из .key или .env."""
    creds = _agent_credentials()
    if not creds:
        return jsonify({"valid": False, "error": "Токен не задан. Добавьте в .key (корень проекта) или в .env: GIGACHAT_CREDENTIALS / GIGACHAT_TOKEN."}), 400
    _ensure_event_loop()
    try:
        from agent.gigachat_agent import validate_credentials
        data = request.get_json(force=True, silent=True) or {}
        scope = (data.get("scope") or "").strip() or _agent_scope()
        validate_credentials(credentials_override=creds, scope_override=scope)
        return jsonify({"valid": True})
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)})


@app.route('/api/agent/status', methods=['GET', 'POST'])
def api_agent_status():
    """Проверка доступности режима агента (GigaChat): ключ из запроса (JSON) или .env."""
    creds = None
    scope = None
    if request.method == 'POST':
        data = request.get_json(force=True, silent=True) or {}
        creds = (data.get("credentials") or "").strip()
        cid = (data.get("client_id") or "").strip()
        csec = (data.get("client_secret") or "").strip()
        if cid and csec:
            import base64
            creds = base64.b64encode(f"{cid}:{csec}".encode()).decode()
        scope = (data.get("scope") or "").strip()
    return jsonify({"available": bool(_agent_credentials(creds)) and (generate_sql_from_description is not None)})


@app.route('/api/agent/token_usage', methods=['GET', 'POST'])
def api_agent_token_usage():
    """Использованные токены и (при пакетной оплате) доступный остаток. Ключ из запроса (JSON) или .env."""
    creds = None
    scope = None
    if request.method == 'POST':
        data = request.get_json(force=True, silent=True) or {}
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
        return jsonify(data)
    except Exception:
        return jsonify({"used": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "available": None})


def _mask_secret(s: str) -> str:
    """Маскирует секреты для логов — ключ никогда не выводится в явном виде."""
    if not s or not isinstance(s, str):
        return ""
    import re
    # Убираем base64-подобные строки (токены, credentials) — мин. 32 символа
    return re.sub(r'[A-Za-z0-9+/]{32,}={0,2}', "***", s)


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
    data = request.get_json(force=True, silent=True) or {}
    creds = (data.get("credentials") or "").strip()
    scope = (data.get("scope") or "").strip()
    verify_ssl = data.get("verify_ssl")
    if verify_ssl is None:
        verify_ssl = True
    else:
        verify_ssl = bool(verify_ssl)
    if not creds:
        return jsonify({"valid": False, "error": "Не указан Token"}), 400
    _ensure_event_loop()
    try:
        from agent.gigachat_agent import validate_credentials
        validate_credentials(
            credentials_override=_agent_credentials(creds),
            scope_override=_agent_scope(scope),
            verify_ssl_override=verify_ssl,
        )
        return jsonify({"valid": True})
    except Exception as e:
        err_msg = str(e).strip() or "Неизвестная ошибка"
        err_lower = err_msg.lower()
        is_ssl = "ssl" in err_lower or "certificate" in err_lower or "eof" in err_lower or "protocol" in err_lower
        if is_ssl and verify_ssl:
            try:
                validate_credentials(
                    credentials_override=_agent_credentials(creds),
                    scope_override=_agent_scope(scope),
                    verify_ssl_override=False,
                )
                os.environ["GIGACHAT_VERIFY_SSL_CERTS"] = "false"
                return jsonify({"valid": True, "verify_ssl_used": False})
            except Exception:
                pass
        if is_ssl:
            if not verify_ssl:
                err_msg = f"{err_msg} — проверка SSL уже отключена. Проверьте сеть, firewall, прокси."
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
        return jsonify({"valid": False, "error": err_msg}), 401


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
    return jsonify(_load_agent_profiles())


@app.route('/api/agent/profiles', methods=['POST'])
def api_agent_profiles_post():
    """Сохранить профили в agent_profiles.json. Тело: [{ name, clientId, scope, tokenFromEnv?, sourceProfile? }, ...]."""
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, list):
        return jsonify({"error": "Ожидается массив профилей"}), 400
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
            profiles.append(item)
    _save_agent_profiles(profiles)
    return jsonify({"ok": True})


@app.route('/api/agent/credentials', methods=['POST'])
def api_agent_credentials():
    """Ключ не сохраняется на сервере. Вводится в UI и передаётся с каждым запросом."""
    return jsonify({"ok": True})


@app.route('/api/agent/generate', methods=['POST'])
def api_agent_generate():
    """Генерация SQL/функции по текстовому описанию через GigaChat. При with_review=True — анализ описания, предупреждение и SQL на проверку."""
    _ensure_event_loop()
    data = request.get_json(force=True, silent=True) or {}
    description = (data.get("description") or "").strip()
    with_review = data.get("with_review") is True
    if not description:
        return jsonify({"error": "Не передано описание"}), 400
    creds = (data.get("credentials") or "").strip()
    if not creds:
        cid, csec = (data.get("client_id") or "").strip(), (data.get("client_secret") or "").strip()
        if cid and csec:
            import base64
            creds = base64.b64encode(f"{cid}:{csec}".encode()).decode()
    use_env = data.get("use_env_credentials") is True
    if not creds and not use_env:
        return jsonify({
            "error": "Ключ не передан. Введите ключ в модальном окне «Ввести ключ» и нажмите «Применить»."
        }), 503
    if not creds and use_env:
        creds = _agent_credentials()
    if not creds:
        return jsonify({
            "error": "Ключ не найден в .key. Введите ключ вручную в модальном окне."
        }), 503
    scope = _agent_scope((data.get("scope") or "").strip())
    if generate_sql_from_description is None:
        return jsonify({
            "error": "Модуль генерации недоступен."
        }), 503
    try:
        if with_review and generate_sql_with_review is not None:
            result = generate_sql_with_review(description, credentials_override=creds)
            return jsonify({
                "sql_or_ddl": result.get("sql_or_ddl", ""),
                "warning": result.get("warning"),
                "analysis": result.get("analysis"),
            })
        sql_or_ddl = generate_sql_from_description(description, credentials_override=creds)
        return jsonify({"sql_or_ddl": sql_or_ddl})
    except Exception as e:
        err_str = str(e)
        if "429" in err_str or "Too Many Requests" in err_str:
            return jsonify({"error": "Превышен лимит запросов GigaChat (429). Подождите и повторите.", "rate_limit_429": True}), 429
        return jsonify({"error": err_str}), 500


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
    """Проверка подключения к БД. Тело: stand_type, user, password, host?, port?, dbname?."""
    data = request.get_json(force=True, silent=True) or {}
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
        return jsonify({"ok": False, "error": "Данные подключения к БД не указаны (логин и пароль обязательны)"}), 400
    try:
        conn = _build_conn_string(stand_type, user, password, host, port, dbname)
        import psycopg2
        c = psycopg2.connect(conn)
        c.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/cache/baseline', methods=['GET'])
def api_cache_baseline_exists():
    """Проверка наличия базового снимка."""
    try:
        from agent.agent_cache_db import baseline_exists
        return jsonify({"exists": baseline_exists()})
    except Exception:
        return jsonify({"exists": False})


@app.route('/api/cache/baseline/save', methods=['POST'])
def api_cache_baseline_save():
    """Сохранить текущее состояние кэшей как базовое. При сбросе данные не будут удаляться ниже этого снимка."""
    try:
        from agent.agent_cache_db import save_baseline
        if save_baseline():
            return jsonify({"ok": True, "message": "Базовое состояние сохранено"})
        return jsonify({"ok": False, "error": "Не удалось сохранить"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/cache/reset', methods=['POST'])
def api_cache_reset():
    """
    Сброс кэшей к базовым настройкам.
    Если есть сохранённый baseline — восстанавливает из него (не ниже текущего состояния).
    Иначе — полная очистка.
    Тело: JSON с полями vector, cache, state (bool) — что сбросить.
    """
    data = request.get_json(force=True, silent=True) or {}
    reset_vector = bool(data.get("vector", False))
    reset_cache = bool(data.get("cache", False))
    reset_state = bool(data.get("state", False))
    if not (reset_vector or reset_cache or reset_state):
        return jsonify({"ok": True, "message": "Ничего не выбрано для сброса", "reset": {}})
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
        return jsonify({"ok": False, "error": str(e)}), 500
    msg = "Восстановлено из базового снимка" if has_baseline else "Сброс выполнен"
    return jsonify({"ok": True, "message": msg, "reset": result, "from_baseline": has_baseline})


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
_jobs: Dict[str, Dict[str, Any]] = {}
_logs: Dict[str, "queue.Queue[str]"] = {}
_performance_monitors: Dict[str, PerformanceMonitor] = {}


def _build_conn_string(stand_type: str, user: str, password: str, host: Optional[str], port: Optional[int], dbname: Optional[str]) -> str:
    """Формирует строку подключения к Greenplum"""
    preset = STANDS.get(stand_type.upper(), {})
    host_val = host or preset.get('host')
    port_val = port or preset.get('port')
    db_val = dbname or preset.get('dbname')
    return f"dbname={db_val} user={user} password={password} host={host_val} port={port_val}"


def _enqueue_log(job_id: str, text: str):
    """Добавляет сообщение в лог задачи"""
    if job_id not in _logs:
        _logs[job_id] = queue.Queue()
    for line in text.splitlines():
        _logs[job_id].put(line + "\n")


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


def _run_discovery_job(job_id: str, payload: Dict[str, Any]):
    """Запуск первого этапа: обнаружение таблиц"""
    _ensure_event_loop()
    buf = _stream_stdout_to_queue(job_id)
    try:
        with redirect_stdout(buf):
            # Явно пишем в лог режим и способ поиска блоков (чтобы в логе было видно отличия от «только логика»)
            analysis_mode = payload.get('analysis_mode', 'logic')
            plan_source = payload.get('plan_source', 'db')
            use_db = payload.get('use_db_connection', True)
            is_pure_agent_mode = analysis_mode == 'hybrid' and not use_db
            mode_label = "чистый агент" if is_pure_agent_mode else ("гибрид" if analysis_mode == 'hybrid' else "логика")
            plan_label = "агент (синтез)" if plan_source == 'agent' else "БД (EXPLAIN)"
            print("=" * 60)
            print(f"Режим анализа: {mode_label}")
            print(f"Источник плана запроса: {plan_label}")
            if analysis_mode == 'hybrid':
                if not payload.get('use_db_connection'):
                    print("Режим: чистый агентский (без БД) — объекты и планы от агента.")
                else:
                    print("Поиск блоков: сначала логика; при частичном результате подключается агент.")
            else:
                print("Поиск логических блоков: логика")
            print("=" * 60)

            # Создаём конфигурацию кластера
            cluster_config = ClusterConfig(
                segments=payload.get('segments', 120),
                ram_per_seg_gb=payload.get('ram_per_seg_gb', 153.6)
            )
            analyzer = DetailedGreenplumFunctionAnalyzer(config=cluster_config)
            use_db = payload.get('use_db_connection')

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
                        _jobs[job_id]['analyzer'] = analyzer
                        _jobs[job_id]['discovery_result'] = result
                        _jobs[job_id]['status'] = 'tables_discovered'
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
                            _jobs[job_id]['analyzer'] = analyzer
                            _jobs[job_id]['discovery_result'] = result
                            _jobs[job_id]['status'] = 'tables_discovered'
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
                _jobs[job_id]['status'] = 'error'
                _jobs[job_id]['error'] = (
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
                    _jobs[job_id]['analyzer'] = analyzer
                    _jobs[job_id]['discovery_result'] = result
                    _jobs[job_id]['status'] = 'tables_discovered'
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
                    _jobs[job_id]['status'] = 'error'
                    _jobs[job_id]['error'] = 'Не удалось подключиться к БД. Проверьте логин и пароль.'
                    return

            # Запускаем обнаружение таблиц
            result = analyzer.discover_tables(payload['ddl'])
            
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
            _jobs[job_id]['analyzer'] = analyzer
            _jobs[job_id]['discovery_result'] = result
            _jobs[job_id]['status'] = 'tables_discovered'

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
        _jobs[job_id]['status'] = 'error'
        err_safe = _mask_secret(str(e))
        _jobs[job_id]['error'] = err_safe
        _enqueue_log(job_id, f"\n❌ Ошибка: {err_safe}\n")
    finally:
        _enqueue_log(job_id, "\n[STREAM_END]\n")


def _run_analysis_job(job_id: str, payload: Dict[str, Any]):
    """Запуск второго этапа: анализ с пользовательскими размерами"""
    _ensure_event_loop()
    buf = _stream_stdout_to_queue(job_id)
    try:
        with redirect_stdout(buf):
            # В логе явно видно режим и источник плана (агент vs логика)
            analysis_mode = _jobs[job_id].get('analysis_mode', 'logic')
            plan_source = _jobs[job_id].get('plan_source', 'db')
            use_db = _jobs[job_id].get('use_db_connection', True)
            is_pure_agent = analysis_mode == 'hybrid' and not use_db
            mode_label = "чистый агент" if is_pure_agent else ("гибрид" if analysis_mode == 'hybrid' else "логика")
            plan_label = "агент (синтез)" if plan_source == 'agent' else "БД (EXPLAIN)"
            print("=" * 60)
            print(f"Режим анализа: {mode_label}")
            print(f"Источник плана запроса: {plan_label}")
            if plan_source == 'agent':
                print("Планы запросов синтезируются агентом (GigaChat).")
            print("=" * 60)

            # Получаем сохранённый анализатор
            analyzer = _jobs[job_id]['analyzer']
            agent_credentials = _jobs[job_id].get('agent_credentials') or _agent_credentials()
            agent_scope = _jobs[job_id].get('agent_scope') or _agent_scope()

            # Запускаем анализ с пользовательскими размерами (режим и источник плана передаём в анализатор)
            params = payload.get('params', [])
            
            # Если параметры не переданы, пробуем взять из сохраненных
            if not params and 'saved_params' in _jobs[job_id]:
                params = _jobs[job_id]['saved_params']
                print(f"🔄 Использованы сохраненные параметры из saved_params: {params}")
            elif not params and 'discovery_result' in _jobs[job_id]:
                # Пробуем взять из discovery_result если есть
                discovery = _jobs[job_id]['discovery_result']
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
            )
            _jobs[job_id]['result'] = result
            _jobs[job_id]['status'] = 'done'
    except Exception as e:
        _jobs[job_id]['status'] = 'error'
        err_safe = _mask_secret(str(e))
        _jobs[job_id]['error'] = err_safe
        _enqueue_log(job_id, f"\n❌ Ошибка: {err_safe}\n")
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
    data = {
        'ddl': ddl,
        'agent_description': agent_description,
        'use_db_connection': use_db,
        'segments': int(request.form.get('segments', 120)),
        'ram_per_seg_gb': float(request.form.get('ram_per_seg_gb', 153.6)),
        'analysis_mode': analysis_mode,
        'plan_source': plan_source,
        'agent_credentials': _agent_credentials(form_creds),
        'agent_scope': _agent_scope(form_scope),
    }
    
    # Проверяем наличие DDL
    if not ddl or not ddl.strip():
        return redirect(url_for('detailed_index', error='ddl_required'))
    
    # Если используем БД, добавляем параметры подключения
    if use_db:
        user = request.form.get('user', '').strip()
        password = request.form.get('password', '').strip()
        
        # Проверяем наличие логина и пароля
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
    
    # Создаём задачу (сохраняем режим и источник плана для этапа анализа)
    job_id = datetime.now().strftime('%Y%m%d%H%M%S%f') + '_disc'
    _jobs[job_id] = {
        'status': 'running',
        'discovery_result': None,
        'analysis_mode': analysis_mode,
        'plan_source': plan_source,
        'use_db_connection': use_db,
        'agent_credentials': data['agent_credentials'],
        'agent_scope': data['agent_scope'],
    }
    _logs[job_id] = queue.Queue()
    
    # Запускаем в отдельном потоке
    th = threading.Thread(target=_run_discovery_job, args=(job_id, data), daemon=True)
    th.start()
    
    return redirect(url_for('discovery_result', job_id=job_id))


@app.route('/discovery/result/<job_id>')
def discovery_result(job_id: str):
    """Страница с результатами обнаружения таблиц"""
    job = _jobs.get(job_id)
    if not job:
        return "Задача не найдена", 404
    mode = job.get('analysis_mode', 'logic')
    use_db = job.get('use_db_connection', True)
    loader_mode = 'agent' if (mode == 'hybrid' and not use_db) else (mode or 'logic')
    return render_template('table_sizes.html', job_id=job_id, status=job['status'], loader_mode=loader_mode)


@app.route('/detailed/analyze', methods=['POST'])
def detailed_analyze():
    """Запуск второго этапа - анализ с пользовательскими размерами"""
    job_id = request.form.get('job_id')
    
    # Проверяем существование задачи
    if job_id not in _jobs:
        return jsonify({'error': 'Задача не найдена'}), 404
    
    # Получаем параметры функции из формы
    params_str = request.form.get('params', '').strip()
    params = [p.strip() for p in params_str.split(',') if p.strip()] if params_str else []
    
    print(f"DEBUG: Получены параметры для анализа из формы: {params}")
    
    # СОХРАНЯЕМ параметры в задаче для последующих запусков
    _jobs[job_id]['saved_params'] = params
    
    # Также сохраняем в discovery_result если он есть
    if 'discovery_result' in _jobs[job_id] and _jobs[job_id]['discovery_result']:
        _jobs[job_id]['discovery_result']['user_params'] = params
        print(f"Сохранены параметры в discovery_result: {params}")
    
    # Очищаем старые данные перед новым запуском
    analyzer = _jobs[job_id].get('analyzer')
    if analyzer:
        analyzer.reset_for_rerun()
        print(f"🔄 Состояние анализатора сброшено для job_id: {job_id}")
    
    # Обновляем статус; сохраняем ключ из задачи (discovery) или .env — не перезаписываем UI-ключ
    _jobs[job_id]['status'] = 'running'
    _jobs[job_id]['agent_credentials'] = _jobs[job_id].get('agent_credentials') or _agent_credentials()
    _jobs[job_id]['agent_scope'] = _jobs[job_id].get('agent_scope') or _agent_scope()
    
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
    monitor = PerformanceMonitor()
    monitor.start_monitoring()
    _performance_monitors[job_id] = monitor
    
    # Запускаем анализ в отдельном потоке
    th = threading.Thread(target=_run_analysis_job, args=(job_id, {
        'params': params,
        'user_sizes': user_sizes
    }), daemon=True)
    th.start()
    
    # Передаём режим в URL, чтобы при 404 (перезапуск сервера) лоадер показывал правильную иконку
    job = _jobs[job_id]
    mode = job.get('analysis_mode', 'logic')
    use_db = job.get('use_db_connection', True)
    loader_mode = 'agent' if (mode == 'hybrid' and not use_db) else (mode if mode else 'logic')
    return redirect(url_for('detailed_result', job_id=job_id) + f'?mode={loader_mode}')


@app.route('/detailed/result/<job_id>')
def detailed_result(job_id: str):
    """Страница с результатами анализа"""
    job = _jobs.get(job_id)
    if not job:
        return "Задача не найдена", 404
    # Режим из URL (при редиректе) или из job
    mode = request.args.get('mode')
    if not mode:
        m = job.get('analysis_mode', 'logic')
        use_db = job.get('use_db_connection', True)
        mode = 'agent' if (m == 'hybrid' and not use_db) else (m or 'logic')
    return render_template('detailed_result.html', job_id=job_id, status=job['status'], loader_mode=mode)


@app.route('/stream/<job_id>')
def stream(job_id: str):
    """Server-Sent Events поток логов"""
    if job_id not in _logs:
        return "Лог не найден", 404

    def event_stream():
        q = _logs[job_id]
        while True:
            line = q.get()
            yield f"data: {line}\n\n"
            if line.strip() == '[STREAM_END]':
                break

    return Response(event_stream(), mimetype='text/event-stream')


@app.route('/status/<job_id>')
def status(job_id: str):
    """Возвращает статус задачи"""
    job = _jobs.get(job_id)
    if not job:
        return jsonify({'status': 'not_found'}), 404
    
    st = job['status']
    res = {'status': st}
    res['analysis_mode'] = job.get('analysis_mode', 'logic')
    res['use_db_connection'] = job.get('use_db_connection', False)
    if 'discovery_result' in job and job['discovery_result']:
        res['use_agent_path'] = job['discovery_result'].get('use_agent_path', False)
    
    # Для этапа обнаружения таблиц
    if st == 'tables_discovered' and job.get('discovery_result'):
        res['discovery'] = job['discovery_result']
    
    # Для завершённого анализа
    if st == 'done' and job.get('result'):
        res['summary'] = {
            'function': job['result'].get('function', 'N/A'),
            'blocks_analyzed': job['result'].get('analyzed_blocks', 0),
            'total_memory_gb': job['result'].get('total_memory_gb', 0),
            'antipattern_added_gb': job['result'].get('antipattern_added_gb', 0),
            'estimated_time_sec': job['result'].get('estimated_time_sec', 0),
            'risk': job['result'].get('risk', 'N/A'),
        }
    
    # Если есть ошибка
    if job.get('error'):
        res['error'] = job['error']
    
    return jsonify(res)


@app.route('/details/<job_id>')
def details(job_id: str):
    """Возвращает полные результаты анализа в JSON"""
    job = _jobs.get(job_id)
    if not job or job['status'] != 'done':
        return jsonify({'error': 'Результат недоступен'}), 400
    out = dict(job['result'])
    out['analysis_mode'] = job.get('analysis_mode', 'logic')
    out['use_db_connection'] = job.get('use_db_connection', False)
    return jsonify(out)


@app.route('/performance/<job_id>')
def get_performance(job_id: str):
    """Возвращает статистику производительности"""
    monitor = _performance_monitors.get(job_id)
    if not monitor:
        return jsonify({'error': 'Монитор не найден'}), 404
    return jsonify(monitor.get_stats())


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)