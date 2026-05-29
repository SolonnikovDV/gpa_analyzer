"""Token usage accounting and provider balance (GigaChat tokens, DeepSeek USD)."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from .credentials import normalize_provider, resolve_credentials

_lock = threading.Lock()
_last_request: Dict[str, Dict[str, int]] = {}


def _usage_fields(usage: Any) -> Dict[str, int]:
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if isinstance(usage, dict):
        pt = int(usage.get("prompt_tokens") or 0)
        ct = int(usage.get("completion_tokens") or 0)
        tt = int(usage.get("total_tokens") or 0)
    else:
        pt = int(getattr(usage, "prompt_tokens", 0) or 0)
        ct = int(getattr(usage, "completion_tokens", 0) or 0)
        tt = int(getattr(usage, "total_tokens", 0) or 0)
    if tt == 0 and (pt or ct):
        tt = pt + ct
    return {
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": tt,
    }


def record_usage(usage: Any, *, provider: str = "gigachat") -> None:
    """Учитывает токены запроса по провайдеру и сохраняет last_request."""
    fields = _usage_fields(usage)
    if not any(fields.values()):
        return
    pid = normalize_provider(provider)
    sessions_delta = 1
    with _lock:
        _last_request[pid] = dict(fields)
    try:
        from .agent_cache_db import add_token_usage_for_provider

        add_token_usage_for_provider(
            pid,
            fields["prompt_tokens"],
            fields["completion_tokens"],
            fields["total_tokens"],
            sessions_delta,
        )
    except Exception:
        pass


def get_last_request_usage(provider: Optional[str] = None) -> Optional[Dict[str, int]]:
    pid = normalize_provider(provider) if provider else None
    with _lock:
        if pid:
            last = _last_request.get(pid)
            return dict(last) if last else None
        if not _last_request:
            return None
        combined = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        for item in _last_request.values():
            combined["prompt_tokens"] += item.get("prompt_tokens", 0)
            combined["completion_tokens"] += item.get("completion_tokens", 0)
            combined["total_tokens"] += item.get("total_tokens", 0)
        return combined if any(combined.values()) else None


def get_provider_totals(provider: str) -> Dict[str, int]:
    pid = normalize_provider(provider)
    try:
        from .agent_cache_db import get_token_usage_for_provider

        row = get_token_usage_for_provider(pid)
        if row:
            return row
    except Exception:
        pass
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "sessions": 0,
    }


def get_all_provider_totals() -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {}
    for pid in ("gigachat", "deepseek"):
        out[pid] = get_provider_totals(pid)
    return out


def fetch_deepseek_balance(credentials: Optional[str] = None) -> Dict[str, Any]:
    """GET /user/balance — остаток на счёте DeepSeek (USD/CNY)."""
    creds = resolve_credentials("deepseek", credentials)
    if not creds:
        return {
            "ok": False,
            "balance_source": "missing_credentials",
            "balance_error": "DEEPSEEK_TOKEN / DEEPSEEK_API_KEY не задан",
        }
    import os

    base = (os.environ.get("DEEPSEEK_API_BASE") or "https://api.deepseek.com").rstrip("/")
    url = f"{base}/user/balance"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {creds}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return {
            "ok": False,
            "balance_source": "deepseek_user_balance_error",
            "balance_error": f"HTTP {e.code}: {body or e.reason}",
        }
    except Exception as e:
        return {
            "ok": False,
            "balance_source": "deepseek_user_balance_error",
            "balance_error": str(e).strip() or type(e).__name__,
        }

    infos = payload.get("balance_infos") or []
    primary = infos[0] if infos else {}
    currency = str(primary.get("currency") or "USD")
    total_balance = str(primary.get("total_balance") or "0")
    return {
        "ok": True,
        "balance_source": "deepseek_user_balance",
        "is_available": bool(payload.get("is_available")),
        "currency": currency,
        "total_balance": total_balance,
        "granted_balance": str(primary.get("granted_balance") or "0"),
        "topped_up_balance": str(primary.get("topped_up_balance") or "0"),
        "balance_infos": infos,
        "available_usd": total_balance if currency.upper() == "USD" else None,
    }


def provider_usage_block(provider: str, *, include_balance: bool = True) -> Dict[str, Any]:
    pid = normalize_provider(provider)
    used = get_provider_totals(pid)
    last = get_last_request_usage(pid)
    block: Dict[str, Any] = {
        "provider": pid,
        "used": used,
        "last_request": last,
    }
    if pid == "deepseek" and include_balance:
        bal = fetch_deepseek_balance(None)
        block.update(bal)
        if bal.get("ok"):
            block["available"] = None
            block["available_label"] = bal.get("total_balance")
            block["available_currency"] = bal.get("currency")
    return block
