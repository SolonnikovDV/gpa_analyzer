"""Infrastructure adapters (persistence, queues) — thin re-exports."""
from __future__ import annotations

from modules.analysis.job_runner import create_job_runner
from modules.analysis.job_store import JobStore, SQLiteJobStore
from modules.analysis.persistence_service import PersistenceService
from modules.analysis.queue_backend import create_redis_connection
from modules.analysis.runtime_preset_store import RuntimePresetStore, SQLiteRuntimePresetStore

__all__ = [
    "PersistenceService",
    "JobStore",
    "SQLiteJobStore",
    "RuntimePresetStore",
    "SQLiteRuntimePresetStore",
    "create_job_runner",
    "create_redis_connection",
]
