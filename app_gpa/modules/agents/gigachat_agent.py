# -*- coding: utf-8 -*-
"""
Агент на базе GigaChat API (GigaChain, документация Сбера).

Используется в соответствии с документацией:
- Ключ авторизации: https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/post-token
- Подсчёт токенов: https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/post-tokens-count
- Остаток токенов: https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/get-balance
- Python SDK: https://developers.sber.ru/docs/ru/gigachain/tools/python/gigachat
- Выбор модели: https://developers.sber.ru/docs/ru/gigachat/guides/selecting-a-model
- LangChain: https://developers.sber.ru/docs/ru/gigachain/tools/python/langchain-gigachat

Поддерживается:
- Генерация SQL/функции по описанию (с кэшем по хешу ввода).
- Второй проход модели — ревизия кода (``revise_sql_code``; в связке ``generate_sql_with_review`` по умолчанию ``code_revision_pass=True``).
- Параметры из .env: GIGACHAT_CREDENTIALS, GIGACHAT_MODEL, GIGACHAT_EMBEDDING_MODEL, GIGACHAT_SCOPE, GIGACHAT_VERIFY_SSL_CERTS,
  GIGACHAT_HTTP_TIMEOUT_SEC / GIGACHAT_TIMEOUT_SEC (таймаут HTTP-клиента SDK для chat/embeddings; иначе у SDK по умолчанию ~30 с и часто «read timed out»).
- Чат: одна модель — ``model_override`` из UI / job, иначе ``GIGACHAT_MODEL``, иначе ``GigaChat-2-Max`` (см. ``CHAT_MODEL_PRIORITY`` только как справочный список для UI).
- Эмбеддинги: одна модель — override, иначе ``GIGACHAT_EMBEDDING_MODEL``, иначе первая из ``EMBEDDING_MODEL_PRIORITY``.
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
from contextlib import contextmanager
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
_token_usage: Dict[str, int] = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "sessions": 0,
    "precached_prompt_tokens": 0,
}


def _usage_get(usage: Any, key: str, default: int = 0) -> int:
    if usage is None:
        return default
    if isinstance(usage, dict):
        v = usage.get(key, default)
    else:
        v = getattr(usage, key, default)
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return default


def _add_usage(usage: Any, *, provider: str = "gigachat") -> None:
    """Учитывает токены и сессии из ответа LLM (usage по документации REST)."""
    if usage is None:
        return
    pt = _usage_get(usage, "prompt_tokens", 0)
    ct = _usage_get(usage, "completion_tokens", 0)
    tt = _usage_get(usage, "total_tokens", 0)
    pc = _usage_get(usage, "precached_prompt_tokens", 0)
    sessions_delta = 1 if (pt or ct or tt) else 0
    with _token_usage_lock:
        _token_usage["prompt_tokens"] += pt
        _token_usage["completion_tokens"] += ct
        _token_usage["total_tokens"] += tt
        _token_usage["precached_prompt_tokens"] += pc
        _token_usage["sessions"] += sessions_delta
    try:
        from .token_usage import record_usage

        record_usage(usage, provider=provider)
        from .agent_cache_db import add_token_usage

        add_token_usage(pt, ct, tt, sessions_delta)
    except Exception:
        pass


def validate_credentials(
    credentials_override: str,
    scope_override: Optional[str] = None,
    verify_ssl_override: Optional[bool] = None,
) -> None:
    """
    Проверяет креды так же «жёстко», как реальные вызовы API.

    Раньше использовался только ``get_balance()``: для части тарифов он даёт 403 (pay-as-you-go)
    или не отражает отзыв/замену ключа в ЛК, из-за чего в UI мог показываться «успех» при уже
    невалидном Authorization key.

    Сейчас: явный OAuth (``get_token`` при наличии в SDK) + один вызов ``POST /tokens/count`` для модели
    из настроек (env/UI). Неверный или отозванный ключ падает на OAuth или на 401.
    """
    kw = _gigachat_client_kwargs(
        credentials_override=credentials_override,
        scope_override=scope_override,
        verify_ssl_override=verify_ssl_override,
    )
    if not kw:
        raise ValueError("Не удалось собрать параметры подключения")
    import time
    for attempt in range(3):
        try:
            with _gigachat_session(kw) as giga:
                # Принудительно обменять Authorization key на access token (ошибки OAuth — здесь)
                if hasattr(giga, "get_token"):
                    tok = giga.get_token()
                    access = ""
                    if tok is not None:
                        access = str(getattr(tok, "access_token", "") or "").strip()
                    if not access:
                        raise RuntimeError(
                            "GigaChat: пустой access token после OAuth. Проверьте ключ в личном кабинете "
                            "(Base64(ClientID:ClientSecret)) или сгенерируйте новый."
                        )
                m = str(kw.get("model") or DEFAULT_MODEL).strip()
                _call_tokens_count_api(giga, ["."], m)
                return
        except Exception as e:
            err_str = str(e).lower()
            is_timeout = "timeout" in err_str or "timed out" in err_str or "handshake" in err_str
            if is_timeout and attempt < 2:
                time.sleep(2)
                continue
            raise


def _gigachat_object_to_dict(obj: Any) -> Dict[str, Any]:
    """Снимок ответа SDK/модели в dict для разбора balance / tokens_count."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    for method in ("model_dump", "dict"):
        fn = getattr(obj, method, None)
        if callable(fn):
            try:
                out = fn()
                if isinstance(out, dict):
                    return out
            except Exception:
                pass
    out: Dict[str, Any] = {}
    for key in (
        "balance",
        "model",
        "name",
        "value",
        "tokens",
        "total_tokens",
        "data",
        "result",
        "object",
        "remaining",
        "input",
    ):
        if hasattr(obj, key):
            out[key] = getattr(obj, key)
    return out


def _parse_get_balance_response(balance_obj: Any) -> Tuple[Optional[int], Optional[int], List[Dict[str, Any]]]:
    """
    Ответ GET /balance (OpenAPI ``Balance``): ``{ "balance": [ { "usage", "value" }, ... ] }``.

    - ``usage`` — название квоты (например ``GigaChat`` или ``Embeddings``).
    - ``value`` — остаток токенов (integer по спецификации).

    Возвращает:
    - ``total_all`` — сумма ``value`` по всем строкам;
    - ``total_chat`` — сумма по строкам, не относящимся к embeddings (для плашки «доступно» в чате);
    - ``rows`` — нормализованные записи для UI.

    См.: https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/get-balance
    """
    if balance_obj is None:
        return None, None, []
    top = balance_obj if isinstance(balance_obj, dict) else _gigachat_object_to_dict(balance_obj)
    if not isinstance(top, dict):
        top = _gigachat_object_to_dict(balance_obj)
    # Обёртка ``data`` (если когда-либо появится у SDK/прокси)
    inner = top.get("data")
    if isinstance(inner, dict) and "balance" in inner:
        top = inner
    entries = top.get("balance")
    if entries is None and not isinstance(balance_obj, dict):
        entries = getattr(balance_obj, "balance", None)
    if entries is None:
        return None, None, []
    if not isinstance(entries, (list, tuple)):
        entries = [entries]
    by_model: List[Dict[str, Any]] = []
    total_all = 0
    total_chat = 0
    has_non_embed_quota = False
    for raw in entries:
        row = raw if isinstance(raw, dict) else _gigachat_object_to_dict(raw)
        usage = str(row.get("usage") or "").strip()
        model = usage or str(row.get("name") or row.get("model") or row.get("id") or "").strip()
        val = row.get("value")
        if val is None:
            val = row.get("tokens") or row.get("total_tokens") or row.get("balance") or row.get("remaining")
        try:
            if val is None:
                num = None
            elif isinstance(val, bool):
                num = None
            elif isinstance(val, (int, float)):
                num = int(val)
            else:
                num = int(str(val).strip())
        except (TypeError, ValueError):
            num = None
        is_embed_quota = "embed" in usage.lower()
        if not is_embed_quota:
            has_non_embed_quota = True
        if num is not None:
            total_all += num
            if not is_embed_quota:
                total_chat += num
        entry: Dict[str, Any] = {
            "usage": usage or None,
            "model": model or "default",
            "tokens": num,
        }
        if val is not None:
            try:
                entry["value"] = int(float(val))
            except (TypeError, ValueError):
                entry["value"] = val
        by_model.append(entry)
    if not by_model:
        return None, None, []
    # Для чата: сумма квот без embeddings; если в ответе только embeddings — показываем сумму всех пакетов
    chat_effective = total_chat if has_non_embed_quota else total_all
    return total_all, chat_effective, by_model


def _call_tokens_count_api(giga: Any, input_strings: List[str], model: str) -> Any:
    """
    POST /tokens/count — тело ``TokensCountBody``: обязательные поля ``model`` и ``input`` (массив строк).

    Ответ 200 — схема ``TokensCount``: JSON-массив объектов ``{ object, tokens, characters }`` по каждой строке ``input``.
    SDK может вернуть объект с полем ``tokens`` — массив тех же элементов (см. пример JS в OpenAPI).

    https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/post-tokens-count
    """
    if not hasattr(giga, "tokens_count"):
        raise AttributeError(
            "Обновите пакет gigachat: нужен метод tokens_count (REST POST /tokens/count)."
        )
    payload_in = [str(s) for s in input_strings]
    try:
        return giga.tokens_count(input_=payload_in, model=model)
    except TypeError:
        try:
            return giga.tokens_count(input=payload_in, model=model)
        except TypeError:
            return giga.tokens_count(model=model, input_=payload_in)


def _tokens_count_row_from_item(it: Any) -> Dict[str, Any]:
    """Одна строка ответа POST /tokens/count: tokens, characters, object (см. SDK TokensCount)."""
    row = it if isinstance(it, dict) else _gigachat_object_to_dict(it)
    n = row.get("tokens")
    if n is None:
        n = row.get("total_tokens") or row.get("value")
    try:
        cnt = int(n) if n is not None else 0
    except (TypeError, ValueError):
        cnt = 0
    ch = row.get("characters")
    try:
        chars = int(ch) if ch is not None else None
    except (TypeError, ValueError):
        chars = None
    obj = row.get("object") or row.get("object_")
    out: Dict[str, Any] = {"tokens": cnt}
    if chars is not None:
        out["characters"] = chars
    if obj:
        out["object"] = obj
    return out


def _tokens_count_items_sequence(result: Any) -> Tuple[Any, Optional[str]]:
    """
    Извлекает последовательность элементов счётчика и опционально ``model`` из ответа POST /tokens/count.

    OpenAPI: тело ответа — массив ``TokensCount`` (по одному объекту на строку ``input``).
    SDK (пример JS в спецификации): ``response.tokens`` — массив тех же объектов.
    """
    if result is None:
        return None, None
    if isinstance(result, (list, tuple)):
        return result, None
    data = result if isinstance(result, dict) else _gigachat_object_to_dict(result)
    if not isinstance(data, dict):
        return None, None
    model = data.get("model") if isinstance(data.get("model"), str) else None
    # Обёртка SDK (пример в OpenAPI): ``{ "tokens": [ { object, tokens, characters }, ... ] }``
    wrapped = data.get("tokens")
    if isinstance(wrapped, list) and wrapped and not isinstance(wrapped[0], (str, bytes, int, float, bool)):
        return wrapped, model
    for key in ("data", "result"):
        seq = data.get(key)
        if isinstance(seq, list) and seq:
            return seq, model
    return None, model


def normalize_tokens_count_response(result: Any, *, model_fallback: Optional[str] = None) -> Dict[str, Any]:
    """
    Приводит ответ POST /tokens/count к единому виду для API/UI.

    Контракт REST (``TokensCount``): массив объектов с полями ``object``, ``tokens``, ``characters``
    (по одному на каждую строку массива ``input`` в запросе ``TokensCountBody``).

    См.: https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/post-tokens-count
    """
    per_input: List[Dict[str, Any]] = []
    model_name: Optional[str] = model_fallback
    if result is None:
        return {"per_input": per_input, "total": 0, "model": model_name}

    items, model_from_resp = _tokens_count_items_sequence(result)
    if model_from_resp:
        model_name = model_from_resp or model_name

    if isinstance(items, (list, tuple)):
        total = 0
        for it in items:
            row = _tokens_count_row_from_item(it)
            per_input.append(row)
            total += int(row.get("tokens") or 0)
        return {"per_input": per_input, "total": total, "model": model_name}

    data: Any = result if isinstance(result, dict) else _gigachat_object_to_dict(result)
    if not isinstance(data, dict):
        return {"per_input": per_input, "total": 0, "model": model_name}

    model_name = (data.get("model") if isinstance(data.get("model"), str) else None) or model_name

    if "total_tokens" in data and not per_input:
        try:
            t = int(data["total_tokens"])
        except (TypeError, ValueError):
            t = 0
        return {"per_input": [{"tokens": t}], "total": t, "model": data.get("model") or model_name}

    total = 0
    tok_scalar = data.get("tokens")
    if isinstance(tok_scalar, int):
        total = tok_scalar
        per_input.append({"tokens": tok_scalar})
    elif not per_input:
        for key in ("total_tokens", "tokens"):
            if key not in data:
                continue
            val = data[key]
            if isinstance(val, list):
                continue
            try:
                total = int(val)
                per_input = [{"tokens": total}]
            except (TypeError, ValueError):
                pass
            break

    return {"per_input": per_input, "total": total, "model": model_name}


def count_input_tokens(
    input_strings: List[str],
    *,
    credentials_override: Optional[str] = None,
    scope_override: Optional[str] = None,
    model_override: Optional[str] = None,
    verify_ssl_override: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Подсчёт токенов через POST /tokens/count (тело ``TokensCountBody``: ``model`` + ``input`` — массив строк).

    Ответ — массив ``TokensCount`` по спецификации (или эквивалент от SDK).
    """
    texts = [str(s) for s in (input_strings or []) if str(s).strip()]
    if not texts:
        return {"ok": True, "per_input": [], "total": 0, "model": None, "error": None}

    kw = _gigachat_client_kwargs(
        credentials_override=credentials_override,
        scope_override=scope_override,
        model_override=model_override,
        verify_ssl_override=verify_ssl_override,
    )
    if not kw:
        return {"ok": False, "per_input": [], "total": 0, "model": None, "error": "Нет учётных данных GigaChat"}

    model = (model_override or "").strip() or str(kw.get("model") or DEFAULT_MODEL)
    try:
        from gigachat import GigaChat
        with _gigachat_session(kw) as giga:
            raw = _call_tokens_count_api(giga, texts, model)
        norm = normalize_tokens_count_response(raw, model_fallback=model)
        norm["ok"] = True
        norm["model"] = norm.get("model") or model
        norm["error"] = None
        return norm
    except Exception as e:
        return {
            "ok": False,
            "per_input": [],
            "total": 0,
            "model": model,
            "error": str(e).strip() or type(e).__name__,
        }


def get_token_usage(
    credentials_override: Optional[str] = None,
    scope_override: Optional[str] = None,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    """Возвращает накопленные токены и остаток (GigaChat: GET /balance; DeepSeek: GET /user/balance)."""
    from .credentials import normalize_provider
    from .token_usage import (
        get_last_request_usage,
        get_provider_totals,
        provider_usage_block,
    )

    pid_filter = normalize_provider(provider) if provider else None
    used = None
    try:
        from .agent_cache_db import get_token_usage_totals
        used = get_token_usage_totals()
    except Exception:
        pass
    if not used:
        with _token_usage_lock:
            used = dict(_token_usage)
    used = dict(used or {})
    if "sessions" not in used:
        used["sessions"] = 0
    with _token_usage_lock:
        used["precached_prompt_tokens"] = int(_token_usage.get("precached_prompt_tokens", 0) or 0)

    used_total = (used or {}).get("total_tokens", 0) or 0
    available: Optional[int] = None
    balance_by_model: List[Dict[str, Any]] = []
    balance_total_all_packages: Optional[int] = None
    balance_source = "unknown"
    balance_error: Optional[str] = None

    try:
        kw = _gigachat_client_kwargs(credentials_override=credentials_override, scope_override=scope_override)
        if kw:
            from gigachat import GigaChat
            with _gigachat_session(kw) as giga:
                balance = giga.get_balance()
                total_all, total_chat, by_model = _parse_get_balance_response(balance)
                balance_by_model = by_model
                balance_total_all_packages = total_all
                if total_chat is not None:
                    available = total_chat
                    balance_source = "get_balance"
    except Exception as e:
        err_text = str(e).strip()
        err_lower = err_text.lower()
        status = getattr(e, "status_code", None)
        if status is None:
            status = getattr(e, "status", None)
        is_403 = status == 403 or "403" in err_text or "permission" in err_lower or "denied" in err_lower
        if is_403:
            balance_error = (
                "GET /balance недоступен (часто при оплате pay-as-you-go; метод только для пакетов токенов). "
                "См. https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/get-balance"
            )
        balance_source = "get_balance_error"

    if available is None:
        scope = (scope_override or os.environ.get("GIGACHAT_SCOPE", DEFAULT_SCOPE) or "").strip()
        if scope.upper() == "GIGACHAT_API_PERS":
            available = max(0, GIGACHAT_LITE_FREEMIUM_TOKENS - used_total)
            balance_source = "freemium_estimate"

    out: Dict[str, Any] = {
        "used": used,
        "available": available,
        "balance_by_model": balance_by_model or None,
        "balance_source": balance_source,
    }
    if balance_total_all_packages is not None:
        out["balance_total_all_packages"] = balance_total_all_packages
    if balance_error:
        out["balance_error"] = balance_error

    by_provider: Dict[str, Any] = {}
    for prov in ("gigachat", "deepseek"):
        if prov == "gigachat":
            g_used = get_provider_totals("gigachat")
            if not any(g_used.values()) and used:
                g_used = dict(used)
            g_block: Dict[str, Any] = {
                "provider": "gigachat",
                "used": g_used,
                "last_request": get_last_request_usage("gigachat"),
                "available": available,
                "balance_by_model": balance_by_model or None,
                "balance_source": balance_source,
            }
            if balance_total_all_packages is not None:
                g_block["balance_total_all_packages"] = balance_total_all_packages
            if balance_error:
                g_block["balance_error"] = balance_error
            by_provider["gigachat"] = g_block
        else:
            by_provider["deepseek"] = provider_usage_block("deepseek")

    out["by_provider"] = by_provider
    out["last_request"] = get_last_request_usage(pid_filter) if pid_filter else get_last_request_usage()

    if pid_filter == "deepseek":
        ds = by_provider["deepseek"]
        out["provider"] = "deepseek"
        out["used"] = ds.get("used") or used
        out["last_request"] = ds.get("last_request")
        out["balance_source"] = ds.get("balance_source")
        out["balance_error"] = ds.get("balance_error")
        out["is_available"] = ds.get("is_available")
        out["currency"] = ds.get("currency")
        out["total_balance"] = ds.get("total_balance")
        out["granted_balance"] = ds.get("granted_balance")
        out["topped_up_balance"] = ds.get("topped_up_balance")
        out["available_usd"] = ds.get("available_usd")
        out["available"] = None
        out["available_label"] = ds.get("total_balance")
        out["available_currency"] = ds.get("currency")
    elif pid_filter == "gigachat":
        out["provider"] = "gigachat"

    return out

# Флаг: один раз залогировать, что sqlite-vec недоступен (список, чтобы не использовать global)
_vec_unavailable_logged = [False]

# Максимум записей в кэше (экономия токенов при неизменном вводе)
MAX_AGENT_CACHE_SIZE = 500
_CACHE_DIR = Path(__file__).resolve().parent
_AGENT_CACHE_FILE = _CACHE_DIR / ".agent_cache.json"

# Справочный список для UI и probe-models (как в документации, раздел «Модели GigaChat»).
# Устаревшие имена вроде GigaChat / GigaChat-2 в выпадающие списки не включаем; в GIGACHAT_MODEL вручную можно задать любое имя, поддерживаемое API.
# Чат: имена поля model — см. https://developers.sber.ru/docs/ru/gigachat/guides/selecting-a-model
# (продукт «GigaChat 2 Lite» в API задаётся как GigaChat-2, не GigaChat-2-Lite — иначе 404 No such model).
CHAT_MODEL_PRIORITY: Tuple[str, ...] = (
    "GigaChat-2-Max",
    "GigaChat-2-Pro",
    "GigaChat-2",
)
# Эмбеддинги: https://developers.sber.ru/docs/ru/gigachat/models/main
EMBEDDING_MODEL_PRIORITY: Tuple[str, ...] = (
    "EmbeddingsGigaR",
    "GigaEmbeddings-3B-2025-09",
    "Embeddings-2",
    "Embeddings",
)
# Обратная совместимость (список для UI / перечислений)
DEFAULT_MODEL = CHAT_MODEL_PRIORITY[0]
MODELS_CHAT = CHAT_MODEL_PRIORITY
# Scope: GIGACHAT_API_PERS (физлица), GIGACHAT_API_B2B, GIGACHAT_API_CORP
DEFAULT_SCOPE = "GIGACHAT_API_PERS"


def _gigachat_http_timeout_seconds() -> float:
    """
    Таймаут для httpx внутри SDK gigachat (секунды, единый для connect/read/write).
    По умолчанию в SDK ~30 с — для chat/completions часто мало (ReadTimeout / «The read operation timed out»).
    """
    raw = (os.environ.get("GIGACHAT_HTTP_TIMEOUT_SEC") or "").strip()
    if not raw:
        raw = (os.environ.get("GIGACHAT_TIMEOUT_SEC") or "").strip()
    if not raw:
        return 180.0
    try:
        v = float(str(raw).replace(",", "."))
        return max(30.0, min(v, 900.0))
    except (TypeError, ValueError):
        return 180.0


# GigaChat 2 Lite Freemium: 900 000 токенов на 12 мес (developers.sber.ru, тарифы физлиц)
# Используется как fallback, когда get_balance() недоступен (403 для pay-as-you-go)
GIGACHAT_LITE_FREEMIUM_TOKENS = 900_000


def _resolved_chat_model(model_override: Optional[str] = None) -> str:
    """Одна чат-модель: из аргумента, иначе GIGACHAT_MODEL, иначе DEFAULT_MODEL."""
    m = (model_override or "").strip() or (os.environ.get("GIGACHAT_MODEL") or "").strip()
    return m or DEFAULT_MODEL


def _resolved_embedding_model(model_override: Optional[str] = None) -> str:
    """Одна модель эмбеддингов: из аргумента, иначе GIGACHAT_EMBEDDING_MODEL, иначе первая из списка."""
    m = (model_override or "").strip() or (os.environ.get("GIGACHAT_EMBEDDING_MODEL") or "").strip()
    return m or EMBEDDING_MODEL_PRIORITY[0]


def _call_gigachat_chat(
    fn,
    credentials_override: Optional[str] = None,
    model_override: Optional[str] = None,
    scope_override: Optional[str] = None,
    client_id_override: Optional[str] = None,
    client_secret_override: Optional[str] = None,
    verify_ssl_override: Optional[bool] = None,
):
    """Один вызов fn(giga) без перебора моделей."""
    m = _resolved_chat_model(model_override)
    kw = _gigachat_client_kwargs(
        credentials_override=credentials_override,
        model_override=m,
        scope_override=scope_override,
        client_id_override=client_id_override,
        client_secret_override=client_secret_override,
        verify_ssl_override=verify_ssl_override,
    )
    if not kw:
        raise RuntimeError(
            "GigaChat не настроен. Задайте ключ в .env (GIGACHAT_CREDENTIALS) или в форме."
        )
    with _gigachat_session(kw) as giga:
        return fn(giga)


def _normalize_input(text: str) -> str:
    """Нормализация ввода для стабильного хеша (пробелы, переносы)."""
    if not text:
        return ""
    return " ".join(text.strip().split())


def _repair_json_invalid_escapes(s: str) -> str:
    """
    В ответах агента в JSON часто попадает SQL с regex (например '\\d', '\\s' в литералах).
    В JSON допустимы только \\\", \\\\, \\/, \\b, \\f, \\n, \\r, \\t, \\uXXXX — иначе JSONDecodeError: Invalid \\escape.
    Дублируем обратный слэш только внутри строковых литералов JSON.
    """
    out: List[str] = []
    i = 0
    n = len(s)
    in_string = False
    while i < n:
        c = s[i]
        if not in_string:
            if c == '"':
                in_string = True
            out.append(c)
            i += 1
            continue
        # inside "..."
        if c == "\\":
            if i + 1 >= n:
                out.append("\\\\")
                i += 1
                continue
            nxt = s[i + 1]
            if nxt in '"\\/bfnrt':
                out.append(c)
                out.append(nxt)
                i += 2
                continue
            if nxt == "u" and i + 5 < n:
                hx = s[i + 2 : i + 6]
                if len(hx) == 4 and all(ch in "0123456789abcdefABCDEF" for ch in hx):
                    out.append(s[i : i + 6])
                    i += 6
                    continue
            out.append("\\\\")
            i += 1
            continue
        if c == '"':
            in_string = False
        out.append(c)
        i += 1
    return "".join(out)


def _json_decode_error_is_bad_escape(exc: BaseException) -> bool:
    if not isinstance(exc, json.JSONDecodeError):
        return False
    msg = (exc.msg or "").lower()
    return "escape" in msg or "invalid" in msg and "\\" in str(exc)


def _parse_first_json(raw: str):
    """Парсит первый JSON-объект/массив из строки. Игнорирует текст после (Extra data)."""
    raw = (raw or "").strip()
    last_err = None
    for start in ("{", "["):
        idx = raw.find(start)
        if idx >= 0:
            chunk = raw[idx:]
            for repaired in (False, True):
                try:
                    text = _repair_json_invalid_escapes(chunk) if repaired else chunk
                    obj, _ = json.JSONDecoder().raw_decode(text)
                    return obj
                except json.JSONDecodeError as e:
                    last_err = e
                    if not repaired and _json_decode_error_is_bad_escape(e):
                        continue
                    break
                except Exception as e:
                    last_err = e
                    break
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
        "timeout": _gigachat_http_timeout_seconds(),
    }
    return kwargs


@contextmanager
def _gigachat_session(kw: Dict[str, Any]):
    from gigachat import GigaChat

    opts = dict(kw or {})
    with GigaChat(**opts) as giga:
        yield giga


def _exception_http_status(exc: BaseException) -> Optional[int]:
    """Пытается извлечь HTTP status из исключения SDK/httpx/requests."""
    seen: set[int] = set()
    e: Optional[BaseException] = exc
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        for attr in ("response", "http_response"):
            r = getattr(e, attr, None)
            if r is not None:
                sc = getattr(r, "status_code", None)
                if sc is not None:
                    try:
                        return int(sc)
                    except (TypeError, ValueError):
                        pass
        sc = getattr(e, "status_code", None)
        if sc is not None:
            try:
                return int(sc)
            except (TypeError, ValueError):
                pass
        e = getattr(e, "__cause__", None) or getattr(e, "original", None)  # type: ignore[assignment]
    return None


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


def _strip_markdown_sql_fence(text: str) -> str:
    """Убирает обёртку ```sql ... ``` из ответа модели."""
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def _governance_enrich(
    step_id: str,
    prompt: str,
    *,
    stack: Optional[str] = None,
    use_governance: bool = True,
) -> str:
    if not use_governance:
        return prompt
    try:
        from .governance.prompt_composer import enrich_prompt

        return enrich_prompt(step_id, stack or "greenplum", prompt)
    except Exception:
        return prompt


def _agent_llm_chat_text(
    prompt: str,
    *,
    step_id: str,
    credentials_override: Optional[str] = None,
    scope_override: Optional[str] = None,
    model_override: Optional[str] = None,
    provider: Optional[str] = None,
    stack: Optional[str] = None,
    use_governance: bool = True,
    timeout_sec: Optional[int] = None,
    multi_agent: Optional[bool] = None,
) -> str:
    """Единая точка LLM-вызова: GigaChat (legacy) или orchestrator (DeepSeek / multi-agent)."""
    from .credentials import normalize_provider
    from .governance.multi_agent_policy import is_multi_agent_enabled

    governed = _governance_enrich(step_id, prompt, stack=stack, use_governance=use_governance)
    pid = normalize_provider(provider)
    if pid == "deepseek" or is_multi_agent_enabled(multi_agent):
        from .orchestrator import AgentOrchestrator

        orch = AgentOrchestrator(
            provider=pid,
            stack=stack or "greenplum",
            credentials_override=credentials_override,
            model_override=model_override,
            scope_override=scope_override,
            multi_agent=multi_agent,
        )
        return (orch.chat(step_id, governed).text or "").strip()

    if not _build_credentials(credentials_override=credentials_override):
        raise RuntimeError("GigaChat не настроен")

    from gigachat import GigaChat

    chat_model = _resolved_chat_model(model_override)
    kw = _gigachat_client_kwargs(
        credentials_override=credentials_override,
        scope_override=scope_override,
        model_override=chat_model,
    )
    if not kw:
        raise RuntimeError("GigaChat client kwargs недоступны")
    to = timeout_sec or int(os.environ.get("GIGACHAT_TIMEOUT_SEC", "120"))

    def _call():
        import asyncio

        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
        with _gigachat_session(kw) as giga:
            response = giga.chat(governed)
            _add_usage(getattr(response, "usage", None))
            return response.choices[0].message.content if response.choices else ""

    with ThreadPoolExecutor(max_workers=1) as ex:
        return (ex.submit(_call).result(timeout=to) or "").strip()


def generate_sql_from_description(
    description: str,
    credentials_override: Optional[str] = None,
    model_override: Optional[str] = None,
    stack: Optional[str] = None,
    use_governance: bool = True,
) -> str:
    """
    Генерирует SQL-запрос или DDL функции по текстовому описанию (GigaChat API).
    credentials_override: ключ из сессии (форма) или None — тогда из env.
    model_override: чат-модель; иначе GIGACHAT_MODEL из env; иначе DEFAULT_MODEL (без перебора моделей).
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

    if not _build_credentials(credentials_override=credentials_override):
        raise RuntimeError(
            "GigaChat не настроен. Задайте ключ в .env (GIGACHAT_CREDENTIALS) или в форме."
        )

    prompt = get_prompt("generate_sql", description=description.strip()) if get_prompt else (
        f"По описанию ниже сгенерируй готовый SQL-запрос или полный DDL функции PL/pgSQL для Greenplum/PostgreSQL.\n"
        f"Выдай только код, без пояснений.\n\nОписание:\n{description.strip()}"
    )
    if use_governance:
        try:
            from .governance.prompt_composer import enrich_prompt
            prompt = enrich_prompt("generate_sql", stack or "greenplum", prompt)
        except Exception:
            pass

    def _generate_sql_chat(giga) -> str:
        response = giga.chat(prompt)
        _add_usage(getattr(response, "usage", None))
        text = response.choices[0].message.content if response.choices else ""
        return _strip_markdown_sql_fence(text)

    result = _call_gigachat_chat(
        _generate_sql_chat,
        credentials_override=credentials_override,
        model_override=model_override,
    )

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
    if not _build_credentials(credentials_override=credentials_override):
        return {"intent": "query", "context_sufficient": True, "warning": None}
    prompt = get_prompt("analyze_description", description=description.strip()[:3000]) if get_prompt else ""
    if not prompt:
        return {"intent": "query", "context_sufficient": True, "warning": None}
    raw = ""
    try:
        def _analyze_chat(giga):
            response = giga.chat(prompt)
            _add_usage(getattr(response, "usage", None))
            return response.choices[0].message.content if response.choices else ""

        raw = _call_gigachat_chat(
            _analyze_chat,
            credentials_override=credentials_override,
        )
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


def revise_sql_code(
    sql: str,
    original_description: str = "",
    credentials_override: Optional[str] = None,
    model_override: Optional[str] = None,
) -> str:
    """
    Второй проход GigaChat: ревизия SQL по правилам цепочки данных, PL/pgSQL, GP и безопасного динамического SQL.
    Кэш не используется. При пустом sql возвращает пустую строку.
    """
    if not sql or not str(sql).strip():
        return (sql or "").strip()
    if not get_prompt:
        return str(sql).strip()
    if not _build_credentials(credentials_override=credentials_override):
        raise RuntimeError(
            "GigaChat не настроен. Задайте ключ в .env (GIGACHAT_CREDENTIALS) или в форме."
        )
    prompt = get_prompt(
        "revise_sql",
        sql=str(sql).strip(),
        description=(original_description or "").strip(),
    )

    def _revise_chat(giga) -> str:
        response = giga.chat(prompt)
        _add_usage(getattr(response, "usage", None))
        text = response.choices[0].message.content if response.choices else ""
        return _strip_markdown_sql_fence(text)

    return _call_gigachat_chat(
        _revise_chat,
        credentials_override=credentials_override,
        model_override=model_override,
    )


def generate_sql_with_review(
    description: str,
    credentials_override: Optional[str] = None,
    model_override: Optional[str] = None,
    *,
    code_revision_pass: bool = True,
) -> Dict[str, Any]:
    """
    Анализирует описание, затем генерирует SQL. Опционально — второй вызов модели (ревизия кода).

    Возвращает sql_or_ddl (после ревизии, если включена), предупреждение о контексте, analysis,
    revision_applied (была ли применена ревизия успешно и текст изменился).
    """
    analysis = analyze_description_for_sql(description, credentials_override=credentials_override)
    sql = generate_sql_from_description(
        description,
        credentials_override=credentials_override,
        model_override=model_override,
    )
    warning = analysis.get("warning")
    if not analysis.get("context_sufficient", True) and not warning:
        warning = (
            "Контекст может быть неполным — проверьте сгенерированный SQL и при необходимости уточните описание."
        )
    out: Dict[str, Any] = {
        "sql_or_ddl": sql,
        "warning": warning,
        "analysis": analysis,
        "revision_applied": False,
        "code_revision_ran": False,
    }
    if code_revision_pass and sql and sql.strip():
        out["code_revision_ran"] = True
        try:
            revised = revise_sql_code(
                sql,
                original_description=description,
                credentials_override=credentials_override,
                model_override=model_override,
            )
            if revised and revised.strip():
                out["revision_applied"] = revised.strip() != sql.strip()
                out["sql_or_ddl"] = revised.strip()
        except Exception as e:
            _log_agent_error("Ревизия SQL", e, None)
            out["sql_or_ddl"] = sql
            out["revision_applied"] = False
    return out


def get_embeddings(
    texts: List[str],
    credentials_override: Optional[str] = None,
    model_override: Optional[str] = None,
) -> List[List[float]]:
    """
    Векторные представления текстов (для RAG и поиска по смыслу).
    Одна модель: model_override → GIGACHAT_EMBEDDING_MODEL → первая из EMBEDDING_MODEL_PRIORITY.
    """
    if not texts:
        return []
    if not _build_credentials(credentials_override=credentials_override):
        raise RuntimeError("GigaChat не настроен. Задайте GIGACHAT_CREDENTIALS.")
    from gigachat import GigaChat

    emb_model = _resolved_embedding_model(model_override)
    kw = _gigachat_client_kwargs(
        credentials_override=credentials_override,
        model_override=emb_model,
    )
    if not kw:
        raise RuntimeError("GigaChat не настроен. Задайте GIGACHAT_CREDENTIALS.")
    with _gigachat_session(kw) as giga:
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
    with _gigachat_session(kw) as giga:
        resp = giga.get_models()
        models = []
        for m in (resp.data or []):
            models.append({"id": getattr(m, "id_", getattr(m, "id", "")), "owned_by": getattr(m, "owned_by", "")})
        return models


def _probe_single_embedding_model(
    model: str,
    credentials_override: str,
    scope_override: Optional[str] = None,
    verify_ssl_override: Optional[bool] = None,
) -> Tuple[bool, Optional[str]]:
    """Один запрос embeddings — без внутреннего перебора моделей."""
    kw = _gigachat_client_kwargs(
        credentials_override=credentials_override,
        scope_override=scope_override,
        model_override=model,
        verify_ssl_override=verify_ssl_override,
    )
    if not kw:
        return False, "Нет учётных данных GigaChat"
    try:
        from gigachat import GigaChat

        with _gigachat_session(kw) as giga:
            giga.embeddings(["."])
        return True, None
    except Exception as e:
        return False, str(e).strip() or type(e).__name__


def probe_models_availability(
    credentials_override: str,
    scope_override: Optional[str] = None,
    verify_ssl_override: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Проверяет доступность чат- и embedding-моделей по цепочкам приоритетов.
    Для чата — POST /tokens/count (минимальный ввод); для эмбеддингов — один вызов embeddings.
    """
    chat_rows: List[Dict[str, Any]] = []
    selected_chat: Optional[str] = None
    for m in CHAT_MODEL_PRIORITY:
        tc = count_input_tokens(
            ["x"],
            credentials_override=credentials_override,
            scope_override=scope_override,
            model_override=m,
            verify_ssl_override=verify_ssl_override,
        )
        ok = bool(tc.get("ok"))
        err = None if ok else (tc.get("error") or "unknown")
        chat_rows.append({"model": m, "ok": ok, "error": err})
        if ok and selected_chat is None:
            selected_chat = m

    emb_rows: List[Dict[str, Any]] = []
    selected_emb: Optional[str] = None
    for m in EMBEDDING_MODEL_PRIORITY:
        ok, err = _probe_single_embedding_model(
            m,
            credentials_override,
            scope_override=scope_override,
            verify_ssl_override=verify_ssl_override,
        )
        emb_rows.append({"model": m, "ok": ok, "error": None if ok else err})
        if ok and selected_emb is None:
            selected_emb = m

    return {
        "chat": chat_rows,
        "embedding": emb_rows,
        "selected_chat": selected_chat,
        "selected_embedding": selected_emb,
        "chat_priority": list(CHAT_MODEL_PRIORITY),
        "embedding_priority": list(EMBEDDING_MODEL_PRIORITY),
    }


def synthesize_plan_for_query(
    query: str,
    objects: list,
    conn_string: Optional[str] = None,
    credentials_override: Optional[str] = None,
    scope_override: Optional[str] = None,
    user_table_sizes: Optional[Dict[str, int]] = None,
    params_and_vars: Optional[Dict[str, str]] = None,
    model_override: Optional[str] = None,
    stack: Optional[str] = None,
    provider: Optional[str] = None,
    use_governance: bool = True,
    multi_agent: Optional[bool] = None,
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
    if not _build_credentials(credentials_override=credentials_override):
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
    prompt = _governance_enrich("synthesize_plan", prompt, stack=stack, use_governance=use_governance)
    text = ""
    timeout_sec = int(os.environ.get("GIGACHAT_TIMEOUT_SEC", "120"))
    max_retries = 3
    import asyncio

    from .credentials import normalize_provider
    from .governance.multi_agent_policy import is_multi_agent_enabled

    pid = normalize_provider(provider)

    def _ensure_loop():
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

    if pid == "deepseek" or is_multi_agent_enabled(multi_agent):
        provider_label = "DeepSeek" if pid == "deepseek" else "GigaChat (multi-agent)"
        for attempt in range(1, max_retries + 1):
            try:
                print(f"   🌐 Запрос к {provider_label} (синтез плана, попытка {attempt}/{max_retries})…")
                text = _agent_llm_chat_text(
                    prompt,
                    step_id="synthesize_plan",
                    credentials_override=credentials_override,
                    scope_override=scope_override,
                    model_override=model_override,
                    provider=pid,
                    stack=stack,
                    use_governance=False,
                    timeout_sec=timeout_sec,
                    multi_agent=multi_agent,
                )
                break
            except Exception as e:
                if attempt >= max_retries:
                    _log_agent_error("Синтез плана (DeepSeek)", e, None)
                    return None
                import time
                time.sleep(2)
        if not text:
            return None
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
            print("   ❌ Агент не вернул валидный план (Plan отсутствует)")
            return None
        node_type = plan.get("Plan", {}).get("Node Type", "?")
        plan_rows = plan.get("Plan", {}).get("Plan Rows", "?")
        print(f"   ✅ План получен от DeepSeek (Node Type: {node_type}, Plan Rows: {plan_rows})")
        _agent_cache_set("synthesize_plan", norm_query + "|" + sizes_str, json.dumps(plan, ensure_ascii=False))
        return plan

    from gigachat import GigaChat

    chat_model = _resolved_chat_model(model_override)
    kw = _gigachat_client_kwargs(
        credentials_override=credentials_override,
        scope_override=scope_override,
        model_override=chat_model,
    )
    if not kw:
        return None
    for attempt in range(1, max_retries + 1):
        try:
            print(
                f"   🌐 Запрос к GigaChat (синтез плана, модель={chat_model}, timeout={timeout_sec}s)…"
            )

            def _call_chat():
                _ensure_loop()
                with _gigachat_session(kw) as giga:
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
    model_override: Optional[str] = None,
    stack: Optional[str] = None,
    provider: Optional[str] = None,
    use_governance: bool = True,
    multi_agent: Optional[bool] = None,
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
    from .credentials import normalize_provider, resolve_credentials

    pid = normalize_provider(provider)
    if pid == "deepseek":
        if not credentials_override and not resolve_credentials("deepseek"):
            return None
    elif not _build_credentials(credentials_override=credentials_override):
        return None

    use_chunking = len(text) > BLOCKS_BO_MAX_CHARS
    if use_chunking:
        chunks = _split_text_chunks(text, chunk_size=BLOCKS_BO_CHUNK_SIZE, overlap=BLOCKS_BO_OVERLAP)
        print(f"   📄 Текст {len(text):,} символов → {len(chunks)} частей (по ~{BLOCKS_BO_CHUNK_SIZE:,} символов)")
    else:
        chunks = [(0, len(text), text)]

    from gigachat import GigaChat
    timeout_bo = BLOCKS_BO_TIMEOUT_SEC
    max_retries_bo = 2

    chat_model = _resolved_chat_model(model_override)
    kw = None
    if pid != "deepseek":
        kw = _gigachat_client_kwargs(
            credentials_override=credentials_override,
            scope_override=scope_override,
            model_override=chat_model,
        )
        if not kw:
            return None

    all_blocks = []
    all_objects = set()
    all_params = []
    all_vars = []
    seen_sql = set()
    raw = ""

    def _process_chunk_prompt(prompt: str, giga) -> str:
        governed = _governance_enrich("blocks_and_objects", prompt, stack=stack, use_governance=use_governance)
        from .governance.multi_agent_policy import is_multi_agent_enabled

        if pid == "deepseek" or is_multi_agent_enabled(multi_agent):
            label = "DeepSeek" if pid == "deepseek" else "GigaChat (multi-agent)"
            for retry in range(max_retries_bo + 1):
                try:
                    return _agent_llm_chat_text(
                        governed,
                        step_id="blocks_and_objects",
                        credentials_override=credentials_override,
                        scope_override=scope_override,
                        model_override=model_override,
                        provider=pid,
                        stack=stack,
                        use_governance=False,
                        timeout_sec=timeout_bo,
                        multi_agent=multi_agent,
                    )
                except (FuturesTimeoutError, Exception) as e:
                    err_str = str(e).lower()
                    if "timeout" in err_str or "timed out" in err_str:
                        if retry < max_retries_bo:
                            import time
                            time.sleep(3)
                            print(f"   ⚠️ Таймаут {label} (попытка {retry + 2}/{max_retries_bo + 1})…")
                            continue
                    raise
            raise RuntimeError(f"Нет ответа от {label}")

        response = None
        for retry in range(max_retries_bo + 1):
            try:
                with ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(giga.chat, governed)
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
        return response.choices[0].message.content if response.choices else ""

    from contextlib import contextmanager

    @contextmanager
    def _giga_session():
        if pid == "deepseek":
            yield None
        else:
            with _gigachat_session(kw) as giga:
                yield giga

    try:
        with _giga_session() as giga:
            for idx, (start, end, chunk) in enumerate(chunks):
                part_num = idx + 1
                total_parts = len(chunks)
                provider_label = "DeepSeek" if pid == "deepseek" else "GigaChat"
                if total_parts > 1:
                    prompt = get_prompt("blocks_and_objects_chunk", part_num=part_num, total_parts=total_parts, text=chunk) if get_prompt else (
                        f"Часть {part_num} из {total_parts} PL/pgSQL. Извлеки блоки и объекты:\n{chunk}"
                    )
                    print(f"   🌐 Запрос к {provider_label} (часть {part_num}/{total_parts}, timeout={timeout_bo}s)…")
                else:
                    prompt = get_prompt("blocks_and_objects", text=chunk) if get_prompt else (
                        f"По тексту PL/pgSQL или SQL определи блоки и объекты. Текст:\n{chunk}"
                    )
                    print(f"   🌐 Запрос к {provider_label} (блоки и объекты, timeout={timeout_bo}s)…")

                raw = _process_chunk_prompt(prompt, giga)
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
    model_override: Optional[str] = None,
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
    if not _build_credentials(credentials_override=credentials_override):
        return []
    prompt = get_prompt("objects_from_sql", text=text[:_max_chars]) if get_prompt else (
        f"Выпиши таблицы и представления из текста. Текст:\n{text[:_max_chars]}"
    )
    raw = ""
    try:
        print(f"   🌐 Запрос к GigaChat (извлечение объектов)…")

        def _objects_chat(giga):
            response = giga.chat(prompt)
            _add_usage(getattr(response, "usage", None))
            return response.choices[0].message.content if response.choices else ""

        raw = _call_gigachat_chat(
            _objects_chat,
            credentials_override=credentials_override,
            scope_override=scope_override,
            model_override=model_override,
        )
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
    model_override: Optional[str] = None,
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
    if not _build_credentials(credentials_override=credentials_override):
        return []
    prompt = get_prompt("missing_objects", found_objects=', '.join(found_objects[:30]), text=function_or_sql_text[:3500]) if get_prompt else (
        f"Определи недостающие объекты для DDL. Уже есть: {', '.join(found_objects[:30])}. Текст:\n{function_or_sql_text[:3500]}"
    )
    text = ""
    try:
        print(f"   🌐 Запрос к GigaChat (проверка недостающих объектов)…")

        def _missing_chat(giga):
            response = giga.chat(prompt)
            _add_usage(getattr(response, "usage", None))
            return response.choices[0].message.content if response.choices else ""

        text = _call_gigachat_chat(
            _missing_chat,
            credentials_override=credentials_override,
            scope_override=scope_override,
            model_override=model_override,
        )
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
    kw = _gigachat_client_kwargs(
        credentials_override=credentials_override,
        model_override=_resolved_chat_model(model_override),
    )
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
    if not _build_credentials(credentials_override=credentials_override):
        raise RuntimeError("GigaChat не настроен. Задайте GIGACHAT_CREDENTIALS.")

    def _invoke_chat(giga):
        response = giga.chat(prompt)
        _add_usage(getattr(response, "usage", None))
        return (response.choices[0].message.content if response.choices else "") or ""

    return _call_gigachat_chat(
        _invoke_chat,
        credentials_override=credentials_override,
        model_override=model_override,
    )


# --- Точки расширения для RAG и LangGraph ---
#
# Гибридный режим (логика сначала, при частичном результате — агент) хорошо ложится на LangGraph:
# узлы = шаги (discover_logic -> check_sufficiency -> [request_ddl | agent_objects_and_vars] -> blocks -> plans -> user_sizes -> recalc),
# рёбра = условные переходы (достаточно объектов? да/нет), состояние = объекты, переменные, планы.
# RAG: get_embeddings() + векторное хранилище -> retrieval -> контекст в промпт.
# LangChain: pip install langchain-gigachat; GigaChat как LLM в цепочках.
# Документация: https://developers.sber.ru/docs/ru/gigachain/overview
