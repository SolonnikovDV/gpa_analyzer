from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Protocol

from .job_contracts import JOB_STATUS_ERROR, JOB_STATUS_RUNNING


SENSITIVE_KEYS = {
    "password",
    "agent_credentials",
    "spark_password",
    "pyspark_password",
}

EXCLUDED_KEYS = {
    "analyzer",
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        safe: Dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if key_str in EXCLUDED_KEYS:
                continue
            if key_str in SENSITIVE_KEYS:
                continue
            safe[key_str] = _json_safe(item)
        return safe
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return [_json_safe(item) for item in sorted(value, key=lambda item: str(item))]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class FileJobStore:
    def __init__(self, root_dir: str) -> None:
        self.root_dir = root_dir
        self.jobs_dir = os.path.join(root_dir, "jobs")
        self.logs_dir = os.path.join(root_dir, "logs")
        os.makedirs(self.jobs_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)

    def _job_path(self, job_id: str) -> str:
        return os.path.join(self.jobs_dir, f"{job_id}.json")

    def _log_path(self, job_id: str) -> str:
        return os.path.join(self.logs_dir, f"{job_id}.log")

    def save_job(self, job_id: str, job: Dict[str, Any]) -> None:
        payload = _json_safe(job)
        payload["job_id"] = job_id
        payload["persisted_at"] = datetime.now(timezone.utc).isoformat()
        with open(self._job_path(job_id), "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    def load_jobs(self) -> Dict[str, Dict[str, Any]]:
        jobs: Dict[str, Dict[str, Any]] = {}
        for filename in sorted(os.listdir(self.jobs_dir)):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self.jobs_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as file:
                    payload = json.load(file)
            except (OSError, json.JSONDecodeError):
                continue
            job_id = str(payload.get("job_id") or filename[:-5])
            payload.pop("job_id", None)
            payload["restored_from_disk"] = True
            if payload.get("status") == JOB_STATUS_RUNNING:
                payload["status"] = JOB_STATUS_ERROR
                payload["error"] = "Задача была прервана перезапуском приложения. Перезапустите анализ."
            jobs[job_id] = payload
        return jobs

    def append_log(self, job_id: str, line: str) -> None:
        with open(self._log_path(job_id), "a", encoding="utf-8") as file:
            file.write(line.rstrip("\n"))
            file.write("\n")

    def read_logs(self, job_id: str) -> List[str]:
        path = self._log_path(job_id)
        if not os.path.isfile(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as file:
                return [line.rstrip("\n") for line in file.readlines()]
        except OSError:
            return []


class JobStore(Protocol):
    def save_job(self, job_id: str, job: Dict[str, Any]) -> None:
        ...

    def load_jobs(self) -> Dict[str, Dict[str, Any]]:
        ...

    def append_log(self, job_id: str, line: str) -> None:
        ...

    def read_logs(self, job_id: str) -> List[str]:
        ...


class SQLiteJobStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
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
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT,
                    payload_json TEXT NOT NULL,
                    persisted_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS job_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    line TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_job_logs_job_id_id ON job_logs(job_id, id)"
            )

    def save_job(self, job_id: str, job: Dict[str, Any]) -> None:
        payload = _json_safe(job)
        payload["job_id"] = job_id
        persisted_at = datetime.now(timezone.utc).isoformat()
        encoded_payload = json.dumps(payload, ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs(job_id, status, payload_json, persisted_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    persisted_at = excluded.persisted_at
                """,
                (job_id, str(payload.get("status") or ""), encoded_payload, persisted_at),
            )

    def load_jobs(self) -> Dict[str, Dict[str, Any]]:
        jobs: Dict[str, Dict[str, Any]] = {}
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT job_id, payload_json FROM jobs ORDER BY persisted_at ASC"
            ).fetchall()
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except json.JSONDecodeError:
                continue
            job_id = str(payload.get("job_id") or row["job_id"])
            payload.pop("job_id", None)
            payload["restored_from_disk"] = True
            if payload.get("status") == JOB_STATUS_RUNNING:
                payload["status"] = JOB_STATUS_ERROR
                payload["error"] = "Задача была прервана перезапуском приложения. Перезапустите анализ."
            jobs[job_id] = payload
        return jobs

    def append_log(self, job_id: str, line: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO job_logs(job_id, line, created_at) VALUES(?, ?, ?)",
                (job_id, line.rstrip("\n"), datetime.now(timezone.utc).isoformat()),
            )

    def read_logs(self, job_id: str) -> List[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT line FROM job_logs WHERE job_id = ? ORDER BY id ASC",
                (job_id,),
            ).fetchall()
        return [str(row["line"]) for row in rows]
