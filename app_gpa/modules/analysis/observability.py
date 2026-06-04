from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from .queue_backend import create_redis_connection


_LOGGER = logging.getLogger("gpa.observability")
if not _LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _LOGGER.addHandler(_handler)
_LOGGER.setLevel(logging.INFO)
_LOGGER.propagate = False

_SENSITIVE_KEYS = {
    "password",
    "agent_credentials",
    "spark_password",
    "pyspark_password",
    "authorization",
    "client_secret",
}


def _sanitize_string(value: str) -> str:
    sanitized = str(value)
    sanitized = re.sub(
        r"(?i)\b(pass" + r"word|passwd|token|credentials|client_secret)\s*[:=]\s*([^\s,;]+)",
        lambda match: f"{match.group(1)}=***",
        sanitized,
    )
    sanitized = re.sub(r"[A-Za-z0-9+/]{32,}={0,2}", "***", sanitized)
    return sanitized


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        normalized: Dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if key_str in _SENSITIVE_KEYS:
                normalized[key_str] = "***"
            else:
                normalized[key_str] = _normalize(item)
        return normalized
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, set):
        return sorted((_normalize(item) for item in value), key=lambda item: str(item))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return _sanitize_string(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _sanitize_string(str(value))


def generate_request_id() -> str:
    return uuid.uuid4().hex


def log_event(event: str, **fields: Any) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
    }
    payload.update({key: _normalize(value) for key, value in fields.items()})
    _LOGGER.info(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def check_sqlite_health(db_path: str) -> Dict[str, Any]:
    try:
        connection = sqlite3.connect(db_path)
        try:
            connection.execute("SELECT 1").fetchone()
        finally:
            connection.close()
        return {"ok": True, "backend": "sqlite", "db_path": db_path}
    except Exception as exc:
        return {"ok": False, "backend": "sqlite", "db_path": db_path, "error": str(exc)}


def check_redis_health(redis_url: str) -> Dict[str, Any]:
    try:
        connection = create_redis_connection(redis_url)
        connection.ping()
        return {"ok": True, "backend": "redis", "redis_url": redis_url}
    except Exception as exc:
        return {"ok": False, "backend": "redis", "redis_url": redis_url, "error": str(exc)}
