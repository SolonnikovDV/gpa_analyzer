from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_bucket(value: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    normalized: Dict[str, Dict[str, Any]] = {}
    for preset_name, preset_payload in value.items():
        name = str(preset_name or "").strip()
        if not name:
            continue
        if isinstance(preset_payload, dict):
            normalized[name] = dict(preset_payload)
        else:
            normalized[name] = {"value": str(preset_payload)}
    return normalized


def _iter_preset_records(raw: Dict[str, Any]):
    for stack_name, stack_bucket in raw.items():
        if not isinstance(stack_bucket, dict):
            continue
        for kind_name, kind_bucket in stack_bucket.items():
            yield str(stack_name), str(kind_name), _normalize_bucket(kind_bucket)


class FileRuntimePresetStore:
    def __init__(self, root_dir: str) -> None:
        self.root_dir = root_dir
        self.path = os.path.join(root_dir, "runtime_presets.json")
        self._lock = threading.Lock()
        os.makedirs(root_dir, exist_ok=True)

    def _load(self) -> Dict[str, Any]:
        if not os.path.isfile(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, payload: Dict[str, Any]) -> None:
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    def list_grouped_values(self) -> Dict[str, Dict[str, Dict[str, str]]]:
        raw = self._load()
        grouped: Dict[str, Dict[str, Dict[str, str]]] = {}
        for stack, stack_bucket in raw.items():
            if not isinstance(stack_bucket, dict):
                continue
            grouped[str(stack)] = {}
            for kind, kind_bucket in stack_bucket.items():
                records = _normalize_bucket(kind_bucket)
                grouped[str(stack)][str(kind)] = {
                    preset_name: str(record.get("value") or "")
                    for preset_name, record in records.items()
                }
        return grouped

    def list_presets(self, stack: Optional[str] = None, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        raw = self._load()
        items: List[Dict[str, Any]] = []
        for stack_name, kind_name, records in _iter_preset_records(raw):
            if stack and stack_name != stack:
                continue
            if kind and kind_name != kind:
                continue
            for preset_name, record in records.items():
                items.append({
                    "stack": stack_name,
                    "kind": kind_name,
                    "name": preset_name,
                    "value": str(record.get("value") or ""),
                    "created_at": record.get("created_at"),
                    "updated_at": record.get("updated_at"),
                })
        items.sort(key=lambda item: (item["stack"], item["kind"], item["name"]))
        return items

    def upsert_preset(self, stack: str, kind: str, name: str, value: str) -> Dict[str, Any]:
        normalized_stack = str(stack or "").strip().lower()
        normalized_kind = str(kind or "").strip().lower()
        normalized_name = str(name or "").strip()
        if not normalized_stack or not normalized_kind or not normalized_name:
            raise ValueError("stack, kind and name are required")
        with self._lock:
            raw = self._load()
            stack_bucket = raw.setdefault(normalized_stack, {})
            kind_bucket = stack_bucket.setdefault(normalized_kind, {})
            existing = kind_bucket.get(normalized_name) if isinstance(kind_bucket, dict) else None
            created_at = existing.get("created_at") if isinstance(existing, dict) else _now_iso()
            record = {
                "value": str(value or ""),
                "created_at": created_at,
                "updated_at": _now_iso(),
            }
            kind_bucket[normalized_name] = record
            self._save(raw)
        return {
            "stack": normalized_stack,
            "kind": normalized_kind,
            "name": normalized_name,
            **record,
        }

    def delete_preset(self, stack: str, kind: str, name: str) -> bool:
        normalized_stack = str(stack or "").strip().lower()
        normalized_kind = str(kind or "").strip().lower()
        normalized_name = str(name or "").strip()
        with self._lock:
            raw = self._load()
            stack_bucket = raw.get(normalized_stack)
            if not isinstance(stack_bucket, dict):
                return False
            kind_bucket = stack_bucket.get(normalized_kind)
            if not isinstance(kind_bucket, dict) or normalized_name not in kind_bucket:
                return False
            del kind_bucket[normalized_name]
            if not kind_bucket:
                stack_bucket.pop(normalized_kind, None)
            if not stack_bucket:
                raw.pop(normalized_stack, None)
            self._save(raw)
        return True


class RuntimePresetStore(Protocol):
    def list_grouped_values(self) -> Dict[str, Dict[str, Dict[str, str]]]:
        ...

    def list_presets(self, stack: Optional[str] = None, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        ...

    def upsert_preset(self, stack: str, kind: str, name: str, value: str) -> Dict[str, Any]:
        ...

    def delete_preset(self, stack: str, kind: str, name: str) -> bool:
        ...


class SQLiteRuntimePresetStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        parent_dir = os.path.dirname(db_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_presets (
                    stack TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    value TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (stack, kind, name)
                )
                """
            )

    def list_grouped_values(self) -> Dict[str, Dict[str, Dict[str, str]]]:
        grouped: Dict[str, Dict[str, Dict[str, str]]] = {}
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT stack, kind, name, value FROM runtime_presets ORDER BY stack, kind, name"
            ).fetchall()
        for row in rows:
            stack = str(row["stack"])
            kind = str(row["kind"])
            name = str(row["name"])
            grouped.setdefault(stack, {}).setdefault(kind, {})[name] = str(row["value"] or "")
        return grouped

    def list_presets(self, stack: Optional[str] = None, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        query = """
            SELECT stack, kind, name, value, created_at, updated_at
            FROM runtime_presets
            WHERE (? IS NULL OR stack = ?)
              AND (? IS NULL OR kind = ?)
            ORDER BY stack, kind, name
        """
        with self._connect() as connection:
            rows = connection.execute(query, (stack, stack, kind, kind)).fetchall()
        return [
            {
                "stack": str(row["stack"]),
                "kind": str(row["kind"]),
                "name": str(row["name"]),
                "value": str(row["value"] or ""),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def upsert_preset(self, stack: str, kind: str, name: str, value: str) -> Dict[str, Any]:
        normalized_stack = str(stack or "").strip().lower()
        normalized_kind = str(kind or "").strip().lower()
        normalized_name = str(name or "").strip()
        if not normalized_stack or not normalized_kind or not normalized_name:
            raise ValueError("stack, kind and name are required")
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT created_at
                    FROM runtime_presets
                    WHERE stack = ? AND kind = ? AND name = ?
                    """,
                    (normalized_stack, normalized_kind, normalized_name),
                ).fetchone()
                created_at = str(row["created_at"]) if row else _now_iso()
                updated_at = _now_iso()
                connection.execute(
                    """
                    INSERT INTO runtime_presets(stack, kind, name, value, created_at, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?)
                    ON CONFLICT(stack, kind, name) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (normalized_stack, normalized_kind, normalized_name, str(value or ""), created_at, updated_at),
                )
        return {
            "stack": normalized_stack,
            "kind": normalized_kind,
            "name": normalized_name,
            "value": str(value or ""),
            "created_at": created_at,
            "updated_at": updated_at,
        }

    def delete_preset(self, stack: str, kind: str, name: str) -> bool:
        normalized_stack = str(stack or "").strip().lower()
        normalized_kind = str(kind or "").strip().lower()
        normalized_name = str(name or "").strip()
        with self._lock:
            with self._connect() as connection:
                cursor = connection.execute(
                    "DELETE FROM runtime_presets WHERE stack = ? AND kind = ? AND name = ?",
                    (normalized_stack, normalized_kind, normalized_name),
                )
                return cursor.rowcount > 0
