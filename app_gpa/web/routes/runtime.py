"""Runtime configuration and preset routes (/api/runtime/*)."""
from __future__ import annotations

from flask import Blueprint, request

from modules.analysis.api_contracts import api_error, api_ok, read_json_object
from modules.analysis.request_validation import RequestValidationError, require_non_empty_string
from modules.analysis.runtime_registry import (
    get_runtime_descriptor,
    get_supported_scenarios,
    get_supported_stacks,
    normalize_scenario,
    normalize_stack,
)
from services.runtime.service import test_runtime
from web.context import _preset_store

bp = Blueprint("runtime", __name__)


@bp.route("/api/runtime/descriptor", methods=["GET", "POST"])
def api_runtime_descriptor():
    """Expose stack/scenario descriptor for multi-stack UI."""
    payload = read_json_object() if request.method == "POST" else request.args
    data = payload or {}
    stack = normalize_stack(data.get("stack"))
    scenario = normalize_scenario(data.get("scenario"))
    descriptor = get_runtime_descriptor(stack, scenario)
    result = {
        "stack": descriptor.stack,
        "scenario": descriptor.scenario,
        "descriptor": descriptor.to_dict(),
        "supported_stacks": get_supported_stacks(),
        "supported_scenarios": get_supported_scenarios(),
    }
    return api_ok(data=result, **result)


@bp.route("/api/runtime/test", methods=["POST"])
def api_runtime_test():
    """Stack-aware runtime access test for GreenPlum, Spark and PySpark."""
    data = read_json_object()
    body, status = test_runtime(data)
    if status >= 400:
        return api_error(
            "runtime_test_failed",
            str(body.get("error") or "Runtime test failed"),
            http_status=status,
            **body,
        )
    return api_ok(data=body, http_status=status, **body)


@bp.route("/api/runtime-presets", methods=["GET", "POST", "DELETE"])
def api_runtime_presets():
    """CRUD для пресетов runtime-подключений."""
    if request.method == "GET":
        stack = normalize_stack(request.args.get("stack")) if request.args.get("stack") else None
        kind = (request.args.get("kind") or "").strip().lower() or None
        if stack or kind:
            items = _preset_store.list_presets(stack=stack, kind=kind)
            return api_ok(data={"items": items}, items=items)
        grouped = _preset_store.list_grouped_values()
        return api_ok(data={"grouped": grouped}, grouped=grouped)

    data = read_json_object()
    stack = normalize_stack(data.get("stack"))
    try:
        kind = require_non_empty_string(data, "kind", code="preset_kind_required").lower()
        name = require_non_empty_string(data, "name", code="preset_name_required")
    except RequestValidationError as exc:
        msg = "kind and name are required" if request.method == "DELETE" else "stack, kind and name are required"
        return api_error(exc.code, msg, http_status=400)

    if request.method == "DELETE":
        deleted = _preset_store.delete_preset(stack, kind, name)
        if not deleted:
            return api_error("preset_not_found", "Preset not found", http_status=404, deleted=False)
        return api_ok(deleted=True)

    value = data.get("value")
    if value is None:
        return api_error("preset_value_required", "Preset value is required", http_status=400)
    try:
        record = _preset_store.upsert_preset(stack, kind, name, str(value))
    except ValueError as exc:
        return api_error("preset_invalid", str(exc), http_status=400)
    return api_ok(data={"preset": record}, preset=record)
