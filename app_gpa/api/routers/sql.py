"""FastAPI SQL lint/completion routes."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from api.contracts import ok_payload
from services.sql import lint_service

router = APIRouter(prefix="/sql", tags=["sql"])


@router.post("/validate")
def post_sql_validate(body: Dict[str, Any]) -> Dict[str, Any]:
    result = lint_service.validate_sql(body)
    payload, _ = ok_payload(data=result, **result)
    return payload


@router.post("/complete")
def post_sql_complete(body: Dict[str, Any]) -> Dict[str, Any]:
    result = lint_service.complete_sql(body)
    payload, _ = ok_payload(data=result, **result)
    return payload
