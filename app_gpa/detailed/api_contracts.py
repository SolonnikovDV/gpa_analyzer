from __future__ import annotations

from typing import Any, Dict, Optional

from flask import Response, jsonify, request


def api_ok(*, data: Optional[Any] = None, http_status: int = 200, **extra: Any) -> Response:
    payload: Dict[str, Any] = {"ok": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    response = jsonify(payload)
    response.status_code = http_status
    return response


def api_error(
    code: str,
    message: str,
    *,
    http_status: int = 400,
    details: Optional[Any] = None,
    **extra: Any,
) -> Response:
    payload: Dict[str, Any] = {
        "ok": False,
        "error": message,
        "error_code": code,
        "error_details": details,
        "message": message,
    }
    payload.update(extra)
    response = jsonify(payload)
    response.status_code = http_status
    return response


def read_json_object() -> Dict[str, Any]:
    payload = request.get_json(force=True, silent=True)
    return payload if isinstance(payload, dict) else {}
