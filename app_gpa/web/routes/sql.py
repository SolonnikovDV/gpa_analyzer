"""SQL lint / completion routes (/api/sql/*)."""
from __future__ import annotations

from flask import Blueprint

from modules.analysis.api_contracts import api_ok, read_json_object
from services.sql import lint_service

bp = Blueprint("sql", __name__)


@bp.route("/api/sql/validate", methods=["POST"])
def api_sql_validate():
    """Stack-aware advisory linting with GreenPlum default compatibility."""
    data = read_json_object()
    result = lint_service.validate_sql(data)
    return api_ok(data=result, **result)


@bp.route("/api/sql/complete", methods=["POST"])
def api_sql_complete():
    """Stack-aware completion with GreenPlum default compatibility."""
    data = read_json_object()
    result = lint_service.complete_sql(data)
    return api_ok(data=result, **result)
