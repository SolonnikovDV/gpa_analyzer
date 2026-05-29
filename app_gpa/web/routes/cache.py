"""Cache management routes (/api/cache/*)."""
from __future__ import annotations

from flask import Blueprint

from modules.analysis.api_contracts import api_error, api_ok, read_json_object
from services.cache import service as cache_service

bp = Blueprint("cache", __name__)


@bp.route("/api/cache/baseline", methods=["GET"])
def api_cache_baseline_exists():
    """Проверка наличия базового снимка."""
    return api_ok(exists=cache_service.baseline_exists())


@bp.route("/api/cache/baseline/save", methods=["POST"])
def api_cache_baseline_save():
    """Сохранить текущее состояние кэшей как базовое."""
    try:
        if cache_service.save_baseline():
            return api_ok(message="Базовое состояние сохранено")
        return api_error("baseline_save_failed", "Не удалось сохранить", http_status=500)
    except Exception as e:
        return api_error("baseline_save_failed", str(e), http_status=500)


@bp.route("/api/cache/reset", methods=["POST"])
def api_cache_reset():
    """Сброс кэшей к базовым настройкам."""
    data = read_json_object()
    reset_vector = bool(data.get("vector", False))
    reset_cache = bool(data.get("cache", False))
    reset_state = bool(data.get("state", False))
    if not (reset_vector or reset_cache or reset_state):
        return api_ok(message="Ничего не выбрано для сброса", reset={})
    try:
        outcome = cache_service.reset_caches(vector=reset_vector, cache=reset_cache, state=reset_state)
        msg = "Восстановлено из базового снимка" if outcome["from_baseline"] else "Сброс выполнен"
        return api_ok(message=msg, reset=outcome["reset"], from_baseline=outcome["from_baseline"])
    except Exception as e:
        return api_error("cache_reset_failed", str(e), http_status=500)
