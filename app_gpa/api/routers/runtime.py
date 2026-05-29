"""FastAPI runtime connectivity and preset routes."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from api.contracts import error_payload, ok_payload
from services.runtime import service as runtime_service

router = APIRouter(tags=["runtime"])


@router.get("/runtime/descriptor")
@router.post("/runtime/descriptor")
async def runtime_descriptor(request: Request) -> Dict[str, Any]:
    if request.method == "POST":
        data = await request.json()
    else:
        data = dict(request.query_params)
    result = runtime_service.runtime_descriptor_payload(data or {})
    payload, _ = ok_payload(data=result, **result)
    return payload


@router.post("/runtime/test")
def runtime_test(body: Dict[str, Any]) -> JSONResponse:
    result, status = runtime_service.test_runtime(body)
    if status >= 400:
        payload, _ = error_payload(
            "runtime_test_failed",
            str(result.get("error") or "Runtime test failed"),
            http_status=status,
            **result,
        )
        return JSONResponse(content=payload, status_code=status)
    payload, _ = ok_payload(data=result, http_status=status, **result)
    return JSONResponse(content=payload, status_code=status)


@router.post("/db/test")
def db_test(body: Dict[str, Any]) -> JSONResponse:
    if "stack" not in body:
        body = {**body, "stack": "greenplum"}
    return runtime_test(body)


@router.api_route("/runtime-presets", methods=["GET", "POST", "DELETE"])
async def runtime_presets(
    request: Request,
    stack: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
) -> JSONResponse:
    query = {"stack": stack, "kind": kind}
    body: Dict[str, Any] = {}
    if request.method in {"POST", "DELETE"}:
        body = await request.json()
    result, status = runtime_service.handle_preset_request(request.method, query=query, body=body)
    if status == 404:
        err, _ = error_payload("preset_not_found", "Preset not found", http_status=404, deleted=False)
        return JSONResponse(content=err, status_code=404)
    if status >= 400:
        code = result.get("code", "preset_error")
        err, _ = error_payload(code, str(result.get("error") or "Preset error"), http_status=status, **result)
        return JSONResponse(content=err, status_code=status)
    ok, _ = ok_payload(**result)
    return JSONResponse(content=ok, status_code=200)
