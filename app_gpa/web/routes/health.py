"""Health check endpoints."""
from __future__ import annotations

from flask import Blueprint

from core.settings import settings
from modules.analysis.api_contracts import api_ok
from modules.analysis.observability import check_redis_health, check_sqlite_health
from web.context import _persistence

bp = Blueprint("health", __name__)


@bp.route("/health/live", methods=["GET"])
def health_live():
    payload = {"status": "live", "checks": {"app": {"ok": True}}}
    return api_ok(data=payload, **payload)


@bp.route("/health/ready", methods=["GET"])
@bp.route("/health", methods=["GET"])
def health_ready():
    checks = {
        "sqlite": check_sqlite_health(_persistence.db_path),
    }
    if settings.job_runner_backend == "queue":
        checks["redis"] = check_redis_health(settings.redis_url)
    else:
        checks["queue_backend"] = {
            "ok": True,
            "backend": settings.job_runner_backend,
            "mode": "local",
        }
    overall_ok = all(bool(item.get("ok")) for item in checks.values())
    payload = {"status": "ready" if overall_ok else "degraded", "checks": checks}
    return api_ok(data=payload, http_status=200 if overall_ok else 503, **payload)
