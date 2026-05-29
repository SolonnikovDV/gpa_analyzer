"""SQL lint and completion use-cases."""
from __future__ import annotations

from typing import Any, Dict, Optional

from modules.analysis.lint.factory import get_linter
from modules.analysis.runtime_registry import get_runtime_descriptor, normalize_scenario, normalize_stack
from modules.analysis.sql_validator import (
    CompositeSQLMetadataProvider,
    OfflineFunctionRegistryProvider,
    PostgresMetadataProvider,
)
from services.runtime.service import build_conn_string


def validate_sql(data: Dict[str, Any]) -> Dict[str, Any]:
    source_text = data.get("source_text") or data.get("sql") or ""
    stack = normalize_stack(data.get("stack"))
    scenario = normalize_scenario(data.get("scenario") or data.get("validation_mode"))
    runtime_descriptor = get_runtime_descriptor(stack, scenario)
    linter = get_linter(stack)
    offline_provider = OfflineFunctionRegistryProvider()
    metadata_provider = offline_provider
    user = (data.get("user") or "").strip()
    password = (data.get("password") or "").strip()
    if runtime_descriptor.capabilities.supports_catalog_metadata and user and password:
        stand_type = (data.get("stand_type") or "").strip() or "PROM"
        host = (data.get("host") or "").strip() or None
        dbname = (data.get("dbname") or "").strip() or None
        port = data.get("port")
        if port is not None and port != "":
            try:
                port = int(port)
            except (TypeError, ValueError):
                port = None
        else:
            port = None
        try:
            conn_string = build_conn_string(stand_type, user, password, host, port, dbname)
            metadata_provider = CompositeSQLMetadataProvider(
                [PostgresMetadataProvider(conn_string), offline_provider]
            )
        except Exception:
            metadata_provider = offline_provider
    return linter.validate(source_text, scenario=scenario, metadata_provider=metadata_provider)


def complete_sql(data: Dict[str, Any]) -> Dict[str, Any]:
    source_text = data.get("source_text") or data.get("sql") or ""
    stack = normalize_stack(data.get("stack"))
    scenario = normalize_scenario(data.get("scenario") or data.get("validation_mode"))
    runtime_descriptor = get_runtime_descriptor(stack, scenario)
    linter = get_linter(stack)
    cursor_index = data.get("cursor_index")
    try:
        cursor_index = int(cursor_index)
    except (TypeError, ValueError):
        cursor_index = len(source_text)
    conn_string: Optional[str] = None
    user = (data.get("user") or "").strip()
    password = (data.get("password") or "").strip()
    if runtime_descriptor.capabilities.supports_catalog_metadata and user and password:
        stand_type = (data.get("stand_type") or "").strip() or "PROM"
        host = (data.get("host") or "").strip() or None
        dbname = (data.get("dbname") or "").strip() or None
        port = data.get("port")
        if port is not None and port != "":
            try:
                port = int(port)
            except (TypeError, ValueError):
                port = None
        else:
            port = None
        try:
            conn_string = build_conn_string(stand_type, user, password, host, port, dbname)
        except Exception:
            conn_string = None
    return linter.complete(source_text, cursor_index, scenario=scenario, conn_string=conn_string)
