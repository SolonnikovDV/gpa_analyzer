"""FastAPI agent cache routes."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.contracts import error_payload, ok_payload
from services.cache import service as cache_service

router = APIRouter(prefix="/cache", tags=["cache"])


@router.get("/baseline")
def cache_baseline_exists() -> Dict[str, Any]:
    payload, _ = ok_payload(exists=cache_service.baseline_exists())
    return payload


@router.post("/baseline/save")
def cache_baseline_save() -> JSONResponse:
    try:
        if cache_service.save_baseline():
            payload, _ = ok_payload(message="Базовое состояние сохранено")
            return JSONResponse(content=payload)
        err, status = error_payload("baseline_save_failed", "Не удалось сохранить", http_status=500)
        return JSONResponse(content=err, status_code=status)
    except Exception as exc:
        err, status = error_payload("baseline_save_failed", str(exc), http_status=500)
        return JSONResponse(content=err, status_code=status)


@router.post("/reset")
def cache_reset(body: Dict[str, Any]) -> JSONResponse:
    reset_vector = bool(body.get("vector", False))
    reset_cache = bool(body.get("cache", False))
    reset_state = bool(body.get("state", False))
    if not (reset_vector or reset_cache or reset_state):
        payload, _ = ok_payload(message="Ничего не выбрано для сброса", reset={})
        return JSONResponse(content=payload)
    try:
        outcome = cache_service.reset_caches(vector=reset_vector, cache=reset_cache, state=reset_state)
        msg = "Восстановлено из базового снимка" if outcome["from_baseline"] else "Сброс выполнен"
        payload, _ = ok_payload(message=msg, **outcome)
        return JSONResponse(content=payload)
    except Exception as exc:
        err, status = error_payload("cache_reset_failed", str(exc), http_status=500)
        return JSONResponse(content=err, status_code=status)
