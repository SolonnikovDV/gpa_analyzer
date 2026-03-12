# -*- coding: utf-8 -*-
"""
Агент на базе GigaChat API (GigaChain, документация Сбера).

Используется в соответствии с документацией:
- Ключ авторизации: https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/post-token
- Python SDK: https://developers.sber.ru/docs/ru/gigachain/tools/python/gigachat
- Выбор модели: https://developers.sber.ru/docs/ru/gigachat/guides/selecting-a-model
- LangChain: https://developers.sber.ru/docs/ru/gigachain/tools/python/langchain-gigachat

Поддерживается:
- Генерация SQL/функции по описанию (с кэшем по хешу ввода).
- Параметры из .env: GIGACHAT_CREDENTIALS, GIGACHAT_MODEL, GIGACHAT_SCOPE, GIGACHAT_VERIFY_SSL_CERTS.
- Эмбеддинги для будущего RAG.
- Точки расширения для LangChain/LangGraph и RAG (векторное хранилище + retrieval).
"""

import base64
import hashlib
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime as dt, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Union, Tuple

try:
    from .agent_prompts import get_prompt
except ImportError:
    get_prompt = None

# Флаг доступности GigaChat (SDK и credentials)
_gigachat_available: Optional[bool] = None

# Учёт использованных токенов (для плашки в UI)
_token_usage_lock = threading.Lock()
_token_usage: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "sessions": 0}


def _add_usage(usage: Any) -> None:
    """Учитывает токены и сессии из ответа GigaChat (usage.prompt_tokens, completion_tokens, total_tokens)."""
    if usage is None:
        return
    pt = getattr(usage, "prompt_tokens", 0) or 0
    ct = getattr(usage, "completion_tokens", 0) or 0
    tt = getattr(usage, "total_tokens", 0) or 0
    sessions_delta = 1 if (pt or ct or tt) else 0
    with _token_usage_lock:
        _token_usage["prompt_tokens"] += pt
        _token_usage["completion_tokens"] += ct
        _token_usage["total_tokens"] += tt
        _token_usage["sessions"] += sessions_delta
    try:
        from .agent_cache_db import add_token_usage
        add_token_usage(pt, ct, tt, sessions_delta)
    except Exception:
        pass


def validate_credentials(
    credentials_override: str,
    scope_override: Optional[str] = None,
    verify_ssl_override: Optional[bool] = None,
) -> None:
    """Проверяет валидность кредов: при неверных — выбрасывает исключение. При таймауте — повтор до 2 раз."""
    kw = _gigachat_client_kwargs(
        credentials_override=credentials_override,
        scope_override=scope_override,
        verify_ssl_override=verify_ssl_override,
    )
    if not kw:
        raise ValueError("Не удалось собрать параметры подключения")
    import time
    last_err = None
    for attempt in range(3):
        try:
            from gigachat import GigaChat
            with GigaChat(**kw) as giga:
                giga.get_balance()
            return
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            is_timeout = "timeout" in err_str or "timed out" in err_str or "handshake" in err_str
            if is_timeout and attempt < 2:
                time.sleep(2)
                continue
            raise


def get_token_usage(credentials_override: Optional[str] = None, scope_override: Optional[str] = None) -> Dict[str, Any]:
    """Возвращает накопленные использованные токены и (если доступно) остаток по пакетам.
    credentials_override: ключ из сессии (форма) или None — тогда из env (нужно для запроса баланса).
    Для GigaChat Lite (GIGACHAT_API_PERS): при недоступности get_balance используем лимит Freemium 900k."""
    # Использовано: из БД (накоплено за всё время), иначе in-memory за текущий процесс
    used = None
    try:
        from .agent_cache_db import get_token_usage_totals
        used = get_token_usage_totals()
    except Exception:
        pass
    if not used:
        with _token_usage_lock:
            used = dict(_token_usage)
    if used and "sessions" not in used:
        used["sessions"] = 0
    used_total = (used or {}).get("total_tokens", 0) or 0
    available: Optional[int] = None
    try:
        kw = _gigachat_client_kwargs(credentials_override=credentials_override, scope_override=scope_override)
        if kw:
            from gigachat import GigaChat
            with GigaChat(**kw) as giga:
                balance = giga.get_balance()
                if balance and getattr(balance, "balance", None):
                    for entry in balance.balance:
                        if getattr(entry, "value", None) is not None:
                            available = (available or 0) + getattr(entry, "value", 0)
    except Exception:
        pass
    # Fallback для GigaChat Lite Freemium: get_balance возвращает 403 при pay-as-you-go
    if available is None:
        scope = scope_override or os.environ.get("GIGACHAT_SCOPE", DEFAULT_SCOPE)
        if scope.upper() in ("GIGACHAT_API_PERS",):
            available = max(0, GIGACHAT_LITE_FREEMIUM_TOKENS - used_total)
    return {"used": used, "available": available}

# Флаг: один раз залогировать, что sqlite-vec недоступен (список, чтобы не использовать global)
_vec_unavailable_logged = [False]

# Максимум записей в кэше (экономия токенов при неизменном вводе)
MAX_AGENT_CACHE_SIZE = 500
_CACHE_DIR = Path(__file__).resolve().parent
_AGENT_CACHE_FILE = _CACHE_DIR / ".agent_cache.json"

# Модели по документации (Выбор модели для генерации)
DEFAULT_MODEL = "GigaChat"  # по умолчанию в SDK
MODELS_CHAT = ("GigaChat", "GigaChat-2", "GigaChat-2-Pro", "GigaChat-2-Max")
# Scope: GIGACHAT_API_PERS (физлица), GIGACHAT_API_B2B, GIGACHAT_API_CORP
DEFAULT_SCOPE = "GIGACHAT_API_PERS"

# GigaChat 2 Lite Freemium: 900 000 токенов на 12 мес (developers.sber.ru, тарифы физлиц)
# Используется как fallback, когда get_balance() недоступен (403 для pay-as-you-go)
GIGACHAT_LITE_FREEMIUM_TOKENS = 900_000


def _normalize_input(text: str) -> str:
    """Нормализация ввода для стабильного хеша (пробелы, переносы)."""
    if not text:
        return ""
    return " ".join(text.strip().split())


def _parse_first_json(raw: str):
    """Парсит первый JSON-объект/массив из строки. Игнорирует текст после (Extra data)."""
    raw = (raw or "").strip()
    last_err = None
    for start in ("{", "["):
        idx = raw.find(start)
        if idx >= 0:
            try:
                obj, _ = json.JSONDecoder().raw_decode(raw[idx:])
                return obj
            except json.JSONDecodeError as e:
                last_err = e
            except Exception as e:
                last_err = e
    if last_err:
        raise last_err
    raise ValueError("JSON не найден в ответе (пустой или некорректный ответ агента)")


_CTX_EMPTY_RESPONSE = "пустой ответ"

def _filter_log_and_type_objects(objects: List[str]) -> List[str]:
    """Исключает tp_*, srv_*, sq_*, seq_* — типы, sequence, служебные объекты (не таблицы/представления)."""
    result = []
    for o in (objects or []):
        s = str(o).strip()
        if not s:
            continue
        # schema.tp_log_instance, schema.srv_*, schema.sq_*, schema.seq_*
        if '.' in s:
            _, tbl = s.split('.', 1)
            if tbl.lower().startswith(('tp_', 'srv_', 'sq_', 'seq_')):
                continue
        elif s.lower().startswith(('tp_', 'srv_', 'sq_', 'seq_')):
            continue
        result.append(s)
    return result


# Паттерн для извлечения schema.table из SQL (fallback когда агент не вернул objects)
_OBJECT_PATTERN = re.compile(
    r'(?:from|join|update|insert\s+into|into|using|table|truncate|delete\s+from)\s+'
    r'([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)',
    re.IGNORECASE
)


def _extract_objects_from_block_sql(blocks: List[Any]) -> List[str]:
    """Извлекает schema.table из SQL блоков (fallback при пустом objects от агента)."""
    seen: set = set()
    result: List[str] = []
    for b in blocks if blocks else []:
        sql = (b.get("sql") if isinstance(b, dict) else "") or ""
        for m in _OBJECT_PATTERN.finditer(sql):
            sch, tbl = m.group(1), m.group(2)
            key = (sch.lower(), tbl.lower())
            if key not in seen:
                seen.add(key)
                result.append(f"{sch}.{tbl}")
    return result


_agent_errors: List[Dict[str, str]] = []


def _log_agent_error(operation: str, e: Exception, context: Optional[str] = None) -> None:
    """Формирует и выводит информативное сообщение об ошибке агента. Сохраняет в _agent_errors для сводки."""
    exc_type = type(e).__name__
    msg = str(e)
    parts = [f"⚠️ [Агент] {operation}: {exc_type}: {msg}"]
    if isinstance(e, json.JSONDecodeError):
        parts.append(f" [строка {e.lineno}, колонка {e.colno}]")
    if context:
        parts.append(f" | Контекст: {context}")
    full_msg = "".join(parts)
    print(full_msg)
    _agent_errors.append({"operation": operation, "type": exc_type, "message": msg, "full": full_msg})


def get_recent_agent_errors() -> List[Dict[str, str]]:
    """Возвращает последние ошибки агента (для вкладки сводки)."""
    return list(_agent_errors)


def clear_agent_errors() -> None:
    """Очищает список ошибок (вызывать в начале нового анализа)."""
    _agent_errors.clear()


def _cache_key(prefix: str, normalized: str) -> str:
    return hashlib.sha256(f"{prefix}:{normalized}".encode("utf-8")).hexdigest()


def _load_agent_cache() -> Dict[str, Dict[str, Any]]:
    """Загружает кэш с диска (если есть)."""
    if not _AGENT_CACHE_FILE.exists():
        return {}
    try:
        with open(_AGENT_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_agent_cache(cache: Dict[str, Dict[str, Any]]) -> None:
    """Сохраняет кэш на диск (ограничение размера по количеству записей)."""
    if len(cache) > MAX_AGENT_CACHE_SIZE:
        keys = list(cache.keys())
        for k in keys[: len(keys) - MAX_AGENT_CACHE_SIZE]:
            cache.pop(k, None)
    try:
        with open(_AGENT_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=0)
    except Exception:
        pass


_agent_cache: Dict[str, Dict[str, Any]] = {}
_agent_cache_loaded = False


def _get_agent_cache() -> Dict[str, Dict[str, Any]]:
    global _agent_cache, _agent_cache_loaded
    if not _agent_cache_loaded:
        _agent_cache = _load_agent_cache()
        _agent_cache_loaded = True
    return _agent_cache


def _agent_cache_get(prefix: str, input_text: str) -> Optional[str]:
    """Возвращает сохранённый результат: сначала SQLite (с проверкой валидности/TTL), затем JSON-файл."""
    try:
        from .agent_cache_db import get as db_get
        out = db_get(prefix, input_text or "")
        if out is not None:
            return out
    except Exception:
        pass
    norm = _normalize_input(input_text)
    key = _cache_key(prefix, norm)
    cache = _get_agent_cache()
    entry = cache.get(key)
    if entry and "result" in entry:
        return entry["result"]
    return None


def _agent_cache_set(prefix: str, input_text: str, result: str) -> None:
    """Сохраняет результат: в SQLite и в JSON-файл (дублирование для совместимости)."""
    try:
        from .agent_cache_db import set as db_set
        db_set(prefix, input_text or "", result)
    except Exception:
        pass
    norm = _normalize_input(input_text)
    key = _cache_key(prefix, norm)
    cache = _get_agent_cache()
    cache[key] = {"result": result, "created": dt.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    _save_agent_cache(cache)


def reset_agent_cache_memory() -> None:
    """Сбросить in-memory кэш агента (после очистки на диске)."""
    global _agent_cache, _agent_cache_loaded
    _agent_cache = {}
    _agent_cache_loaded = False


def _check_gigachat() -> bool:
    global _gigachat_available
    if _gigachat_available is not None:
        return _gigachat_available
    try:
        creds = _build_credentials()
        _gigachat_available = bool(creds)
    except Exception:
        _gigachat_available = False
    return _gigachat_available


def is_agent_available() -> bool:
    """Проверяет, настроен ли GigaChat (GIGACHAT_CREDENTIALS или GIGACHAT_TOKEN в .env/сессии)."""
    return _check_gigachat()


def _build_credentials(
    credentials_override: Optional[str] = None,
    client_id_override: Optional[str] = None,
    client_secret_override: Optional[str] = None,
) -> str:
    """
    Собирает credentials для GigaChat. OAuth: Authorization = Base64(ClientID:ClientSecret).
    Источники: credentials_override (готовый ключ) или client_id+client_secret, или env.
    """
    if (credentials_override or "").strip():
        return (credentials_override or "").strip()
    cid = (client_id_override or "").strip() or os.environ.get("GIGACHAT_CLIENT_ID", "").strip()
    csec = (client_secret_override or "").strip() or os.environ.get("GIGACHAT_CLIENT_SECRET", "").strip()
    if cid and csec:
        return base64.b64encode(f"{cid}:{csec}".encode()).decode()
    return (
        os.environ.get("GIGACHAT_CREDENTIALS")
        or os.environ.get("GIGACHAT_TOKEN")
        or ""
    ).strip()


def _gigachat_client_kwargs(
    credentials_override: Optional[str] = None,
    model_override: Optional[str] = None,
    scope_override: Optional[str] = None,
    client_id_override: Optional[str] = None,
    client_secret_override: Optional[str] = None,
    verify_ssl_override: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Собирает аргументы для GigaChat() по документации SDK.
    credentials: готовый ключ Base64(ClientID:ClientSecret) или собирается из Client ID + Client Secret.
    scope: GIGACHAT_API_PERS (физлица), GIGACHAT_API_B2B, GIGACHAT_API_CORP.
    """
    credentials = _build_credentials(
        credentials_override=credentials_override,
        client_id_override=client_id_override,
        client_secret_override=client_secret_override,
    )
    if not credentials:
        return {}

    model = (model_override or "").strip() or os.environ.get("GIGACHAT_MODEL", "").strip() or DEFAULT_MODEL
    scope = (scope_override or "").strip() or os.environ.get("GIGACHAT_SCOPE", "").strip() or DEFAULT_SCOPE
    if verify_ssl_override is not None:
        verify_ssl = verify_ssl_override
    else:
        verify_ssl = os.environ.get("GIGACHAT_VERIFY_SSL_CERTS", "false").strip().lower() in ("1", "true", "yes")

    kwargs: Dict[str, Any] = {
        "credentials": credentials,
        "model": model,
        "scope": scope,
        "verify_ssl_certs": verify_ssl,
    }
    return kwargs


def get_client(
    credentials_override: Optional[str] = None,
    model_override: Optional[str] = None,
    scope_override: Optional[str] = None,
):
    """
    Возвращает настроенный экземпляр GigaChat (контекстный менеджер не обязателен, но рекомендуется with).
    Используется для чата, эмбеддингов, get_models() и т.д.
    """
    from gigachat import GigaChat
    kw = _gigachat_client_kwargs(credentials_override, model_override, scope_override)
    if not kw:
        raise RuntimeError("Задайте GIGACHAT_CREDENTIALS в .env или ключ в форме.")
    return GigaChat(**kw)


def generate_sql_from_description(
    description: str,
    credentials_override: Optional[str] = None,
    model_override: Optional[str] = None,
) -> str:
    """
    Генерирует SQL-запрос или DDL функции по текстовому описанию (GigaChat API).
    credentials_override: ключ из сессии (форма) или None — тогда из env.
    model_override: модель (GigaChat-2, GigaChat-2-Pro, GigaChat-2-Max) или из env GIGACHAT_MODEL.
    Кэш: повторный запрос с тем же описанием не вызывает API.
    """
    if not description or not description.strip():
        return ""

    cached = _agent_cache_get("generate_sql", description)
    if cached is not None:
        return cached

    # Семантический кэш (sqlite-vec) — переиспользование при похожем описании, экономия токенов
    try:
        from .agent_cache_db import get_similar, set_vector, vec_available
        if vec_available():
            print("[sqlite-vec] Семантический кэш включён, проверка похожих запросов…", flush=True)
            emb = get_embeddings([description.strip()], credentials_override=credentials_override)
            if emb and len(emb) > 0:
                similar = get_similar("generate_sql", emb[0], threshold=0.97)
                if similar is not None:
                    resp, sim = similar
                    print(f"[sqlite-vec] Попадание: использован ответ по похожему описанию (similarity={sim:.2f}), API не вызывался", flush=True)
                    _agent_cache_set("generate_sql", description, resp)
                    return resp
    except Exception as e:
        print(f"[sqlite-vec] Проверка семантического кэша: {e}", flush=True)

    try:
        from .agent_cache_db import vec_available
        if not vec_available() and not _vec_unavailable_logged[0]:
            _vec_unavailable_logged[0] = True
            print("[sqlite-vec] Недоступен (установите: pip install sqlite-vec), используется только точный кэш", flush=True)
    except Exception:
        pass

    kw = _gigachat_client_kwargs(credentials_override=credentials_override, model_override=model_override)
    if not kw:
        raise RuntimeError(
            "GigaChat не настроен. Задайте ключ в .env (GIGACHAT_CREDENTIALS) или в форме."
        )

    from gigachat import GigaChat

    prompt = get_prompt("generate_sql", description=description.strip()) if get_prompt else (
        f"По описанию ниже сгенерируй готовый SQL-запрос или полный DDL функции PL/pgSQL для Greenplum/PostgreSQL.\n"
        f"Выдай только код, без пояснений.\n\nОписание:\n{description.strip()}"
    )
    with GigaChat(**kw) as giga:
        response = giga.chat(prompt)
        _add_usage(getattr(response, "usage", None))
        text = response.choices[0].message.content if response.choices else ""
        if text.strip().startswith("```"):
            lines = text.strip().split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        result = text.strip()

    _agent_cache_set("generate_sql", description, result)
    try:
        from .agent_cache_db import set_vector, vec_available
        if vec_available():
            emb = get_embeddings([description.strip()], credentials_override=credentials_override)
            if emb and len(emb) > 0:
                set_vector("generate_sql", description, emb[0], result)
                print("[sqlite-vec] Вектор сохранён для переиспользования при похожих запросах", flush=True)
    except Exception as e:
        print(f"[sqlite-vec] Сохранение вектора: {e}", flush=True)
    return result


def analyze_description_for_sql(
    description: str,
    credentials_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Анализирует текстовое описание: намерение (функция/запрос), недостающие части,
    достаточность контекста, предупреждение при недостаточности. Результат для передачи
    в генерацию и отображения пользователю «на проверку».
    """
    if not description or not description.strip():
        return {"intent": "query", "context_sufficient": True, "warning": None}
    norm = _normalize_input(description[:4000])
    cached = _agent_cache_get("analyze_description", norm)
    if cached is not None:
        try:
            return json.loads(cached)
        except Exception:
            pass
    kw = _gigachat_client_kwargs(credentials_override=credentials_override)
    if not kw:
        return {"intent": "query", "context_sufficient": True, "warning": None}
    prompt = get_prompt("analyze_description", description=description.strip()[:3000]) if get_prompt else ""
    if not prompt:
        return {"intent": "query", "context_sufficient": True, "warning": None}
    raw = ""
    try:
        from gigachat import GigaChat
        with GigaChat(**kw) as giga:
            response = giga.chat(prompt)
            _add_usage(getattr(response, "usage", None))
            raw = response.choices[0].message.content if response.choices else ""
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines)
        data = _parse_first_json(raw)
        out = {
            "intent": data.get("intent") or "query",
            "return_type": data.get("return_type"),
            "signature_params": data.get("signature_params") or [],
            "data_sources": data.get("data_sources") or [],
            "dataflow": data.get("dataflow"),
            "result_target": data.get("result_target"),
            "context_sufficient": data.get("context_sufficient", True),
            "warning": data.get("warning"),
        }
        _agent_cache_set("analyze_description", norm, json.dumps(out, ensure_ascii=False))
        return out
    except Exception as e:
        ctx = _CTX_EMPTY_RESPONSE if not (raw and raw.strip()) else None
        _log_agent_error("Анализ описания", e, ctx)
    return {"intent": "query", "context_sufficient": True, "warning": None}


def generate_sql_with_review(
    description: str,
    credentials_override: Optional[str] = None,
    model_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Анализирует описание, затем генерирует SQL. Возвращает SQL для проверки пользователем,
    предупреждение о недостаточности контекста и результат анализа (intent, недостающие части и т.д.).
    """
    analysis = analyze_description_for_sql(description, credentials_override=credentials_override)
    sql = generate_sql_from_description(
        description,
        credentials_override=credentials_override,
        model_override=model_override,
    )
    warning = analysis.get("warning") if not analysis.get("context_sufficient") else None
    return {
        "sql_or_ddl": sql,
        "warning": warning,
        "analysis": analysis,
    }


def get_embeddings(
    texts: List[str],
    credentials_override: Optional[str] = None,
) -> List[List[float]]:
    """
    Векторные представления текстов (для RAG и поиска по смыслу).
    Модель эмбеддингов задаётся API по умолчанию (Embeddings и др.).
    """
    if not texts:
        return []
    kw = _gigachat_client_kwargs(credentials_override=credentials_override)
    if not kw:
        raise RuntimeError("GigaChat не настроен. Задайте GIGACHAT_CREDENTIALS.")
    from gigachat import GigaChat
    with GigaChat(**kw) as giga:
        result = giga.embeddings(texts)
        out = []
        for item in (result.data or []):
            out.append(getattr(item, "embedding", []) or [])
        return out


def get_models_list(credentials_override: Optional[str] = None) -> List[Dict[str, Any]]:
    """Список доступных моделей (GET /models)."""
    kw = _gigachat_client_kwargs(credentials_override=credentials_override)
    if not kw:
        return []
    from gigachat import GigaChat
    with GigaChat(**kw) as giga:
        resp = giga.get_models()
        models = []
        for m in (resp.data or []):
            models.append({"id": getattr(m, "id_", getattr(m, "id", "")), "owned_by": getattr(m, "owned_by", "")})
        return models


def synthesize_plan_for_query(
    query: str,
    objects: list,
    conn_string: Optional[str] = None,
    credentials_override: Optional[str] = None,
    scope_override: Optional[str] = None,
    user_table_sizes: Optional[Dict[str, int]] = None,
    params_and_vars: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Синтезирует план запроса для Greenplum в формате EXPLAIN (JSON) без выполнения в БД.
    objects: список (schema, table) или имён таблиц; user_table_sizes: { "schema.table": rows }.
    Возвращает dict с ключом "Plan" (корневой узел с Node Type, Plan Rows, Plans и т.д.).
    """
    if not query or not query.strip():
        return None
    sql_preview = (query[:80] + "…") if len(query) > 80 else query
    print(f"🤖 [Агент] Синтез плана: SQL «{sql_preview}», таблиц: {len(objects)}, размеры: {len(user_table_sizes or {})}")
    # Кэш по хешу запроса и размеров
    norm_query = _normalize_input(query[:2000])
    sizes_str = json.dumps(user_table_sizes or {}, sort_keys=True) if user_table_sizes else ""
    cached = _agent_cache_get("synthesize_plan", norm_query + "|" + sizes_str)
    if cached is not None:
        try:
            plan = json.loads(cached)
            node_type = plan.get("Plan", {}).get("Node Type", "?")
            plan_rows = plan.get("Plan", {}).get("Plan Rows", "?")
            print(f"   📦 Результат из кэша (Node Type: {node_type}, Plan Rows: {plan_rows})")
            return plan
        except Exception:
            pass
    kw = _gigachat_client_kwargs(credentials_override=credentials_override, scope_override=scope_override)
    if not kw:
        return None
    tables_desc = ""
    if user_table_sizes:
        tables_desc = "Таблицы и оценки строк: " + ", ".join(f"{t}: {r}" for t, r in list(user_table_sizes.items())[:20])
    if not objects and tables_desc:
        tables_desc = "Парсер не извлёк таблицы из SQL. " + tables_desc
    params_str = ""
    if params_and_vars:
        params_str = "Параметры и переменные (для интерпретации): " + ", ".join(f"{k}={v}" for k, v in list(params_and_vars.items())[:15])
    prompt = get_prompt("synthesize_plan", tables_desc=tables_desc, params_and_vars=params_str, query=query[:3000]) if get_prompt else (
        f"По SQL для Greenplum/PostgreSQL сформируй план в JSON. SQL:\n{query[:3000]}"
    )
    text = ""
    timeout_sec = int(os.environ.get("GIGACHAT_TIMEOUT_SEC", "120"))
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            print(f"   🌐 Запрос к GigaChat (синтез плана, timeout={timeout_sec}s)…")
            from gigachat import GigaChat
            import asyncio

            def _ensure_loop():
                try:
                    asyncio.get_event_loop()
                except RuntimeError:
                    asyncio.set_event_loop(asyncio.new_event_loop())

            def _call_chat():
                _ensure_loop()
                with GigaChat(**kw) as giga:
                    response = giga.chat(prompt)
                    _add_usage(getattr(response, "usage", None))
                    return response.choices[0].message.content if response.choices else ""

            with ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(_call_chat)
                text = future.result(timeout=timeout_sec) or ""
            text = text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                text = "\n".join(lines)
            plan = _parse_first_json(text)
            if "Plan" not in plan and isinstance(plan, dict) and len(plan) == 1:
                plan = {"Plan": list(plan.values())[0]}
            if "Plan" not in plan:
                print(f"   ❌ Агент не вернул валидный план (Plan отсутствует)")
                return None
            node_type = plan.get("Plan", {}).get("Node Type", "?")
            plan_rows = plan.get("Plan", {}).get("Plan Rows", "?")
            print(f"   ✅ План получен от GigaChat (Node Type: {node_type}, Plan Rows: {plan_rows})")
            _agent_cache_set("synthesize_plan", norm_query + "|" + sizes_str, json.dumps(plan, ensure_ascii=False))
            return plan
        except json.JSONDecodeError as e:
            if attempt < max_retries:
                print(f"   ⚠️ Ошибка парсинга JSON GigaChat (попытка {attempt}/{max_retries}). Задержка обработки данных — повтор…")
                import time
                time.sleep(2)
            else:
                ctx = _CTX_EMPTY_RESPONSE if not (text and text.strip()) else None
                _log_agent_error("Синтез плана", e, ctx)
                return None
        except FuturesTimeoutError:
            if attempt < max_retries:
                print(f"   ⚠️ Таймаут GigaChat (попытка {attempt}/{max_retries}). Задержка обработки — повтор…")
                import time
                time.sleep(2)
            else:
                print(f"   ❌ Таймаут GigaChat ({timeout_sec}s) при синтезе плана")
                _log_agent_error("Синтез плана", TimeoutError(f"Таймаут API {timeout_sec}s"), None)
                return None
        except Exception as e:
            ctx = _CTX_EMPTY_RESPONSE if not (text and text.strip()) else None
            _log_agent_error("Синтез плана", e, ctx)
            return None


# GigaChat 128K контекст ≈ 350K символов (с запасом на промпт и ответ)
MAX_CHARS_SINGLE = 350000
CHUNK_SIZE = 70000
CHUNK_OVERLAP = 8000

# Для blocks_and_objects: меньший порог и чанки, чтобы избежать ReadTimeout
BLOCKS_BO_MAX_CHARS = 35000
BLOCKS_BO_CHUNK_SIZE = 28000
BLOCKS_BO_OVERLAP = 3000
BLOCKS_BO_TIMEOUT_SEC = int(os.environ.get("GIGACHAT_BLOCKS_TIMEOUT_SEC", "180"))


def _split_text_chunks(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[Tuple[int, int, str]]:
    """Разбивает текст на чанки с перекрытием. Возвращает [(start, end, chunk), ...]."""
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunk = text[start:end]
        if chunk.strip():
            chunks.append((start, end, chunk))
        start = end - overlap if end < n else n
    return chunks


def get_blocks_and_objects_from_ddl(
    text: str,
    credentials_override: Optional[str] = None,
    scope_override: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Чистый агентский режим: агент сам находит исполняемые блоки и объекты в DDL функции/SQL.
    При длинном тексте (>MAX_CHARS_SINGLE) — разбиение на чанки, обработка по частям, склейка результатов.
    Возвращает {"blocks": [...], "objects": [...], "function_params": [...], "variables": [...]}
    """
    if not text or not text.strip():
        return None
    print("🤖 [Агент] Чистый режим: извлечение блоков и объектов из DDL…")
    norm = _normalize_input(text)
    cached = _agent_cache_get("blocks_and_objects", norm)
    if cached is not None:
        try:
            data = json.loads(cached)
            blocks = data.get("blocks") or []
            objects = list(data.get("objects") or [])
            if blocks:
                extracted = _extract_objects_from_block_sql(blocks)
                extracted_filtered = _filter_log_and_type_objects(extracted)
                objects = list(dict.fromkeys(objects + extracted_filtered))
            data["objects"] = _filter_log_and_type_objects(objects)
            print(f"   📦 Результат из кэша: блоков {len(blocks)}, объектов {len(data.get('objects', []))}",
                  f", параметров {len(data.get('function_params', []))}, переменных {len(data.get('variables', []))}")
            return data
        except Exception:
            pass
    kw = _gigachat_client_kwargs(credentials_override=credentials_override, scope_override=scope_override)
    if not kw:
        return None

    use_chunking = len(text) > BLOCKS_BO_MAX_CHARS
    if use_chunking:
        chunks = _split_text_chunks(text, chunk_size=BLOCKS_BO_CHUNK_SIZE, overlap=BLOCKS_BO_OVERLAP)
        print(f"   📄 Текст {len(text):,} символов → {len(chunks)} частей (по ~{BLOCKS_BO_CHUNK_SIZE:,} символов)")
    else:
        chunks = [(0, len(text), text)]

    all_blocks = []
    all_objects = set()
    all_params = []
    all_vars = []
    seen_sql = set()
    raw = ""

    try:
        from gigachat import GigaChat
        timeout_bo = BLOCKS_BO_TIMEOUT_SEC
        max_retries_bo = 2

        with GigaChat(**kw) as giga:
            for idx, (start, end, chunk) in enumerate(chunks):
                part_num = idx + 1
                total_parts = len(chunks)
                if total_parts > 1:
                    prompt = get_prompt("blocks_and_objects_chunk", part_num=part_num, total_parts=total_parts, text=chunk) if get_prompt else (
                        f"Часть {part_num} из {total_parts} PL/pgSQL. Извлеки блоки и объекты:\n{chunk}"
                    )
                    print(f"   🌐 Запрос к GigaChat (часть {part_num}/{total_parts}, timeout={timeout_bo}s)…")
                else:
                    prompt = get_prompt("blocks_and_objects", text=chunk) if get_prompt else (
                        f"По тексту PL/pgSQL или SQL определи блоки и объекты. Текст:\n{chunk}"
                    )
                    print(f"   🌐 Запрос к GigaChat (блоки и объекты, timeout={timeout_bo}s)…")

                response = None
                for retry in range(max_retries_bo + 1):
                    try:
                        with ThreadPoolExecutor(max_workers=1) as ex:
                            future = ex.submit(giga.chat, prompt)
                            response = future.result(timeout=timeout_bo)
                        break
                    except (FuturesTimeoutError, Exception) as e:
                        err_str = str(e).lower()
                        if "timeout" in err_str or "timed out" in err_str:
                            if retry < max_retries_bo:
                                import time
                                time.sleep(3)
                                print(f"   ⚠️ Таймаут (попытка {retry + 2}/{max_retries_bo + 1})…")
                                continue
                        raise
                if response is None:
                    raise RuntimeError("Нет ответа от GigaChat")
                _add_usage(getattr(response, "usage", None))
                raw = response.choices[0].message.content if response.choices else ""
                raw = raw.strip()
                if raw.startswith("```"):
                    lines = raw.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    raw = "\n".join(lines)
                data = _parse_first_json(raw)
                # Агент может вернуть массив вместо объекта: [{"blocks":...}] или [{"type":"INSERT","sql":"..."},...]
                if isinstance(data, list):
                    if data and isinstance(data[0], dict) and ("blocks" in data[0] or "objects" in data[0]):
                        data = data[0]
                    else:
                        data = {"blocks": [b for b in data if isinstance(b, dict) and b], "objects": [], "function_params": [], "variables": []}
                if not isinstance(data, dict):
                    data = {}
                blocks = data.get("blocks") or []
                objects = data.get("objects") or []
                function_params = data.get("function_params") or []
                variables = data.get("variables") or []
                if not isinstance(blocks, list):
                    blocks = []
                if not isinstance(objects, list):
                    objects = [str(o) for o in (objects,) if o]
                for b in blocks:
                    if isinstance(b, dict) and b:
                        sql = str(b.get("sql", "")).strip()
                        sql_norm = " ".join(sql.split())[:500]
                        if sql_norm and sql_norm not in seen_sql:
                            seen_sql.add(sql_norm)
                            all_blocks.append({"type": str(b.get("type", "OTHER")), "sql": sql})
                for o in objects:
                    if o and str(o).strip():
                        all_objects.add(str(o).strip())
                if function_params and not all_params:
                    all_params = [str(p).strip() for p in function_params if p and str(p).strip()]
                if variables:
                    for v in variables:
                        if v and str(v).strip().lower() != "log":
                            all_vars.append(str(v).strip())
                    all_vars = list(dict.fromkeys(all_vars))

        objects_clean = _filter_log_and_type_objects(list(all_objects))
        # Дополняем объектами из блоков: агент может пропустить (напр. v_stg_t_netto_incom_outcom vs v_stg_t_netto_incom_outcom_m)
        if all_blocks:
            extracted = _extract_objects_from_block_sql(all_blocks)
            extracted_filtered = _filter_log_and_type_objects(extracted)
            objects_clean = list(dict.fromkeys(objects_clean + extracted_filtered))
        out = {
            "blocks": all_blocks,
            "objects": objects_clean,
            "function_params": all_params,
            "variables": all_vars,
        }
        block_types = [b.get("type", "?") for b in out["blocks"][:5]]
        print(f"   ✅ Результат от GigaChat: блоков {len(out['blocks'])}", f"({', '.join(block_types)}{'…' if len(out['blocks']) > 5 else ''})",
              f", объектов {len(out['objects'])}", f", параметров {len(out['function_params'])}", f", переменных {len(out['variables'])}")
        _agent_cache_set("blocks_and_objects", norm, json.dumps(out, ensure_ascii=False))
        return out
    except Exception as e:
        ctx = _CTX_EMPTY_RESPONSE if not (raw and raw.strip()) else None
        _log_agent_error("Извлечение блоков и объектов", e, ctx)
    return None


def get_objects_from_sql_or_function(
    text: str,
    credentials_override: Optional[str] = None,
    scope_override: Optional[str] = None,
) -> List[str]:
    """
    Извлекает список объектов (таблицы/представления) из текста SQL или DDL функции.
    Используется в чистом агентском режиме (без БД): агент находит объекты по тексту.
    Возвращает список полных имён вида "schema.name".
    """
    if not text or not text.strip():
        return []
    print("🤖 [Агент] Гибрид (без БД): извлечение объектов из текста…")
    _max_chars = MAX_CHARS_SINGLE
    norm = _normalize_input(text[:_max_chars])
    cached = _agent_cache_get("objects_from_sql", norm)
    if cached is not None:
        try:
            out = _filter_log_and_type_objects(json.loads(cached))
            print(f"   📦 Результат из кэша: объектов {len(out)}")
            return out
        except Exception:
            pass
    kw = _gigachat_client_kwargs(credentials_override=credentials_override, scope_override=scope_override)
    if not kw:
        return []
    prompt = get_prompt("objects_from_sql", text=text[:_max_chars]) if get_prompt else (
        f"Выпиши таблицы и представления из текста. Текст:\n{text[:_max_chars]}"
    )
    raw = ""
    try:
        print(f"   🌐 Запрос к GigaChat (извлечение объектов)…")
        from gigachat import GigaChat
        with GigaChat(**kw) as giga:
            response = giga.chat(prompt)
            _add_usage(getattr(response, "usage", None))
            raw = response.choices[0].message.content if response.choices else ""
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines)
        arr = _parse_first_json(raw)
        if isinstance(arr, list):
            out = [str(x).strip() for x in arr if x and str(x).strip()]
        elif isinstance(arr, dict) and "objects" in arr:
            out = [str(x).strip() for x in (arr.get("objects") or []) if x and str(x).strip()]
        else:
            out = []
        if out:
            out = _filter_log_and_type_objects(out)
            print(f"   ✅ Результат от GigaChat: объектов {len(out)} — {', '.join(out[:5])}{'…' if len(out) > 5 else ''}")
            _agent_cache_set("objects_from_sql", norm, json.dumps(out, ensure_ascii=False))
        else:
            print(f"   ⚠️ Агент вернул пустой список объектов")
        return out
    except Exception as e:
        ctx = _CTX_EMPTY_RESPONSE if not (raw and raw.strip()) else None
        _log_agent_error("Извлечение объектов из SQL", e, ctx)
    return []


def get_missing_objects_for_ddl(
    function_or_sql_text: str,
    found_objects: List[str],
    credentials_override: Optional[str] = None,
    scope_override: Optional[str] = None,
) -> List[str]:
    """
    Агент сверяет список найденных объектов с текстом и возвращает список имён объектов,
    для которых может понадобиться DDL (например, представления, которых нет в found_objects).
    found_objects: список полных имён "schema.table" или "schema.view".
    """
    if not function_or_sql_text or not function_or_sql_text.strip():
        return []
    print(f"🤖 [Агент] Гибрид: проверка недостающих объектов (найдено: {len(found_objects)})…")
    norm = _normalize_input(function_or_sql_text[:4000]) + "|" + ",".join(sorted(found_objects)[:50])
    cached = _agent_cache_get("missing_objects", norm)
    if cached is not None:
        try:
            out = json.loads(cached)
            print(f"   📦 Результат из кэша: недостающих {len(out)}")
            return out
        except Exception:
            pass
    kw = _gigachat_client_kwargs(credentials_override=credentials_override, scope_override=scope_override)
    if not kw:
        return []
    prompt = get_prompt("missing_objects", found_objects=', '.join(found_objects[:30]), text=function_or_sql_text[:3500]) if get_prompt else (
        f"Определи недостающие объекты для DDL. Уже есть: {', '.join(found_objects[:30])}. Текст:\n{function_or_sql_text[:3500]}"
    )
    text = ""
    try:
        print(f"   🌐 Запрос к GigaChat (проверка недостающих объектов)…")
        from gigachat import GigaChat
        with GigaChat(**kw) as giga:
            response = giga.chat(prompt)
            _add_usage(getattr(response, "usage", None))
            text = response.choices[0].message.content if response.choices else ""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        arr = _parse_first_json(text)
        if isinstance(arr, list):
            out = [str(x).strip() for x in arr if x]
        elif isinstance(arr, dict):
            out = [str(x).strip() for x in (arr.get("objects") or arr.get("missing") or []) if x]
        else:
            out = []
        if out:
            print(f"   ✅ Результат от GigaChat: недостающих {len(out)} — {', '.join(out[:5])}{'…' if len(out) > 5 else ''}")
            _agent_cache_set("missing_objects", norm, json.dumps(out, ensure_ascii=False))
        else:
            print(f"   ✅ Результат от GigaChat: недостающих объектов нет")
        return out
    except Exception as e:
        ctx = _CTX_EMPTY_RESPONSE if not (text and text.strip()) else None
        _log_agent_error("Проверка недостающих объектов", e, ctx)
    return []


# --- Опциональная интеграция LangChain / GigaChain ---

def _langchain_giga_chat(credentials_override: Optional[str] = None, model_override: Optional[str] = None):
    """
    Если установлен langchain-gigachat — возвращает LLM для цепочек и RAG.
    Документация: https://developers.sber.ru/docs/ru/gigachain/tools/python/langchain-gigachat
    """
    try:
        from langchain_gigachat.chat_models import GigaChat
    except ImportError:
        return None
    kw = _gigachat_client_kwargs(credentials_override=credentials_override, model_override=model_override)
    if not kw:
        return None
    return GigaChat(
        credentials=kw["credentials"],
        model=kw.get("model", DEFAULT_MODEL),
        scope=kw.get("scope", DEFAULT_SCOPE),
        verify_ssl_certs=kw.get("verify_ssl_certs", True),
    )


def invoke_with_prompt(
    prompt: str,
    credentials_override: Optional[str] = None,
    model_override: Optional[str] = None,
    use_langchain: bool = False,
) -> str:
    """
    Универсальный вызов: один промпт -> ответ модели.
    use_langchain=True: использовать langchain_gigachat (если установлен) для совместимости с цепочками/RAG.
    """
    if use_langchain:
        llm = _langchain_giga_chat(credentials_override, model_override)
        if llm is not None:
            out = llm.invoke(prompt)
            return getattr(out, "content", str(out))
    kw = _gigachat_client_kwargs(credentials_override=credentials_override, model_override=model_override)
    if not kw:
        raise RuntimeError("GigaChat не настроен. Задайте GIGACHAT_CREDENTIALS.")
    from gigachat import GigaChat
    with GigaChat(**kw) as giga:
        response = giga.chat(prompt)
        _add_usage(getattr(response, "usage", None))
        return (response.choices[0].message.content if response.choices else "") or ""


# --- Точки расширения для RAG и LangGraph ---
#
# Гибридный режим (логика сначала, при частичном результате — агент) хорошо ложится на LangGraph:
# узлы = шаги (discover_logic -> check_sufficiency -> [request_ddl | agent_objects_and_vars] -> blocks -> plans -> user_sizes -> recalc),
# рёбра = условные переходы (достаточно объектов? да/нет), состояние = объекты, переменные, планы.
# RAG: get_embeddings() + векторное хранилище -> retrieval -> контекст в промпт.
# LangChain: pip install langchain-gigachat; GigaChat как LLM в цепочках.
# Документация: https://developers.sber.ru/docs/ru/gigachain/overview
