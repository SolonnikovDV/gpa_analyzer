"""Runtime connectivity and preset use-cases."""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

from core.settings import settings
from modules.analysis.persistence_service import PersistenceService
from modules.analysis.request_validation import RequestValidationError, require_non_empty_string
from modules.analysis.runtime_preset_store import RuntimePresetStore
from modules.analysis.runtime_registry import (
    get_runtime_descriptor,
    get_supported_scenarios,
    get_supported_stacks,
    normalize_scenario,
    normalize_stack,
)

STANDS: Dict[str, Dict[str, Any]] = {
    "PROM": {
        "host": "gp_dns_gp_rozn4.gp.df.sbrf.ru",
        "port": 5432,
        "dbname": "gp_rozn2",
    },
    "LD": {
        "host": "gp_dns_pkap1150.gp.df.sbrf.ru",
        "port": 5432,
        "dbname": "gp_rozn2",
    },
    "IFT": {
        "host": "tvlds-sdpgp0478.qa.df.sbrf.ru",
        "port": 5432,
        "dbname": "iftadbcom",
    },
    "Пользовательский": {
        "host": None,
        "port": None,
        "dbname": None,
    },
}


@lru_cache(maxsize=1)
def get_preset_store() -> RuntimePresetStore:
    persistence = PersistenceService(settings.runtime_store_dir, settings.persistence_db_path)
    return persistence.runtime_preset_store


def build_conn_string(
    stand_type: str,
    user: str,
    password: str,
    host: Optional[str],
    port: Optional[int],
    dbname: Optional[str],
) -> str:
    preset = STANDS.get(stand_type.upper(), STANDS.get(stand_type, {}))
    host_val = host or preset.get("host")
    port_val = port or preset.get("port")
    db_val = dbname or preset.get("dbname")
    return f"dbname={db_val} user={user} password={password} host={host_val} port={port_val}"


def runtime_descriptor_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    stack = normalize_stack(data.get("stack"))
    scenario = normalize_scenario(data.get("scenario"))
    descriptor = get_runtime_descriptor(stack, scenario)
    return {
        "stack": descriptor.stack,
        "scenario": descriptor.scenario,
        "descriptor": descriptor.to_dict(),
        "supported_stacks": get_supported_stacks(),
        "supported_scenarios": get_supported_scenarios(),
    }


def test_runtime(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    stack = normalize_stack(data.get("stack"))
    scenario = normalize_scenario(data.get("scenario"))
    descriptor = get_runtime_descriptor(stack, scenario)

    if stack == "greenplum":
        stand_type = (data.get("stand_type") or "").strip() or "PROM"
        user = (data.get("user") or "").strip()
        password = (data.get("password") or "").strip()
        host = (data.get("host") or "").strip() or None
        port = data.get("port")
        if port is not None and port != "":
            try:
                port = int(port)
            except (TypeError, ValueError):
                port = None
        dbname = (data.get("dbname") or "").strip() or None
        if not user or not password:
            return {
                "ok": False,
                "error": descriptor.ui.get("connection_missing") or "Не указаны логин и пароль.",
            }, 400
        try:
            conn = build_conn_string(stand_type, user, password, host, port, dbname)
            import psycopg2

            connection = psycopg2.connect(conn)
            connection.close()
            return {"ok": True, "message": descriptor.ui.get("connection_success")}, 200
        except Exception as exc:
            return {"ok": False, "error": str(exc)}, 500

    master_url = (data.get("master_url") or "").strip()
    if not master_url:
        return {
            "ok": False,
            "error": descriptor.ui.get("connection_missing") or "Не указан runtime endpoint.",
        }, 400
    return {
        "ok": True,
        "message": descriptor.ui.get("connection_success"),
        "stack": stack,
        "runtime_note": "Runtime test works in MVP mode for this stack and validates access parameters without a native connector.",
    }, 200


def list_presets(*, stack: Optional[str] = None, kind: Optional[str] = None) -> Dict[str, Any]:
    store = get_preset_store()
    if stack or kind:
        return {"items": store.list_presets(stack=stack, kind=kind)}
    return {"grouped": store.list_grouped_values()}


def upsert_preset(data: Dict[str, Any]) -> Dict[str, Any]:
    stack = normalize_stack(data.get("stack"))
    kind = require_non_empty_string(data, "kind", code="preset_kind_required").lower()
    name = require_non_empty_string(data, "name", code="preset_name_required")
    value = data.get("value")
    if value is None:
        raise ValueError("Preset value is required")
    record = get_preset_store().upsert_preset(stack, kind, name, str(value))
    return {"preset": record}


def delete_preset(data: Dict[str, Any]) -> bool:
    stack = normalize_stack(data.get("stack"))
    kind = require_non_empty_string(data, "kind", code="preset_kind_required").lower()
    name = require_non_empty_string(data, "name", code="preset_name_required")
    return get_preset_store().delete_preset(stack, kind, name)


def handle_preset_request(method: str, *, query: Dict[str, Any], body: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    if method == "GET":
        stack = normalize_stack(query.get("stack")) if query.get("stack") else None
        kind = (query.get("kind") or "").strip().lower() or None
        return list_presets(stack=stack, kind=kind), 200

    stack = normalize_stack(body.get("stack"))
    try:
        if method == "DELETE":
            deleted = delete_preset(body)
            if not deleted:
                return {"deleted": False, "error": "Preset not found"}, 404
            return {"deleted": True}, 200
        record_payload = upsert_preset(body)
        return record_payload, 200
    except RequestValidationError as exc:
        if method == "DELETE":
            return {"error": "kind and name are required", "code": exc.code}, 400
        return {"error": "stack, kind and name are required", "code": exc.code}, 400
    except ValueError as exc:
        return {"error": str(exc), "code": "preset_invalid"}, 400
