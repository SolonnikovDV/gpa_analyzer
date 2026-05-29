"""Shared API response helpers (Flask + FastAPI)."""
from __future__ import annotations

from typing import Any, Dict, Optional


def ok_payload(*, data: Optional[Any] = None, http_status: int = 200, **extra: Any) -> tuple[Dict[str, Any], int]:
    payload: Dict[str, Any] = {"ok": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return payload, http_status


def error_payload(
    code: str,
    message: str,
    *,
    http_status: int = 400,
    details: Optional[Any] = None,
    **extra: Any,
) -> tuple[Dict[str, Any], int]:
    payload: Dict[str, Any] = {
        "ok": False,
        "error": message,
        "error_code": code,
        "error_details": details,
        "message": message,
    }
    payload.update(extra)
    return payload, http_status
