"""FastAPI health-check routes.

/api/health/live   — shallow liveness probe (always 200 if the process is up)
/api/health/ready  — deep readiness probe (checks SQLite store and Redis)
/api/health        — alias for /ready
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

router = APIRouter(tags=["health"])


def _check_sqlite() -> Dict[str, Any]:
    try:
        from core.paths import VAR_DIR
        import sqlite3
        db_path = VAR_DIR / "jobs.db"
        if not db_path.exists():
            return {"ok": True, "note": "db not yet created"}
        with sqlite3.connect(str(db_path), timeout=2) as conn:
            conn.execute("SELECT 1")
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _check_redis() -> Dict[str, Any]:
    try:
        from core.settings import settings
        if not settings.redis_url:
            return {"ok": True, "note": "redis not configured"}
        import redis
        r = redis.from_url(settings.redis_url, socket_connect_timeout=2)
        r.ping()
        return {"ok": True}
    except ImportError:
        return {"ok": True, "note": "redis-py not installed"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/live")
def health_live() -> dict:
    return {"ok": True, "status": "live"}


@router.get("/ready")
@router.get("")
def health_ready() -> dict:
    sqlite = _check_sqlite()
    redis = _check_redis()
    all_ok = sqlite["ok"] and redis["ok"]
    return {
        "ok": all_ok,
        "status": "ready" if all_ok else "degraded",
        "checks": {
            "sqlite": sqlite,
            "redis": redis,
        },
    }
