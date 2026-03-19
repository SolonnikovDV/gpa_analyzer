from __future__ import annotations

from typing import Final, FrozenSet


JOB_STATUS_RUNNING: Final[str] = "running"
JOB_STATUS_TABLES_DISCOVERED: Final[str] = "tables_discovered"
JOB_STATUS_DONE: Final[str] = "done"
JOB_STATUS_ERROR: Final[str] = "error"
JOB_STATUS_NOT_FOUND: Final[str] = "not_found"

ACTIVE_JOB_STATUSES: Final[FrozenSet[str]] = frozenset(
    {
        JOB_STATUS_RUNNING,
        JOB_STATUS_TABLES_DISCOVERED,
    }
)

TERMINAL_JOB_STATUSES: Final[FrozenSet[str]] = frozenset(
    {
        JOB_STATUS_DONE,
        JOB_STATUS_ERROR,
    }
)


def is_terminal_job_status(status: str) -> bool:
    return status in TERMINAL_JOB_STATUSES
