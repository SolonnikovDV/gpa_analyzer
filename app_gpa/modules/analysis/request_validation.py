from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class RequestValidationError(Exception):
    code: str
    message: str


def require_non_empty_string(data: Dict[str, Any], field_name: str, *, code: str | None = None) -> str:
    value = str(data.get(field_name) or "").strip()
    if value:
        return value
    raise RequestValidationError(code or f"{field_name}_required", f"Field '{field_name}' is required")


def expect_list_payload(payload: Any, *, code: str = "invalid_payload_list", message: str = "Ожидается массив") -> List[Any]:
    if isinstance(payload, list):
        return payload
    raise RequestValidationError(code, message)
