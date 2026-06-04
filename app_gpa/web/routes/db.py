"""Database connectivity test route (/api/db/test).

Backward-compatible alias — delegates to runtime test service.
"""
from __future__ import annotations

from flask import Blueprint

from modules.analysis.api_contracts import api_error, api_ok, read_json_object
from services.runtime.service import test_runtime

bp = Blueprint("db", __name__)


@bp.route("/api/db/test", methods=["POST"])
def api_db_test():
    """Backward-compatible runtime test endpoint."""
    data = read_json_object()
    if "stack" not in data:
        data["stack"] = "greenplum"
    body, status = test_runtime(data)
    if status >= 400:
        return api_error(
            "runtime_test_failed",
            str(body.get("error") or "Runtime test failed"),
            http_status=status,
            **body,
        )
    return api_ok(data=body, http_status=status, **body)
