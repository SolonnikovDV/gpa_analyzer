from __future__ import annotations

import queue
from typing import Any, Dict, Optional

from .job_store import JobStore


class JobService:
    def __init__(self, job_store: JobStore, jobs: Dict[str, Dict[str, Any]], logs: Dict[str, "queue.Queue[str]"]) -> None:
        self.job_store = job_store
        self.jobs = jobs
        self.logs = logs

    def create_job(self, job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.jobs[job_id] = dict(payload)
        self.persist_job(job_id)
        self.ensure_log_queue(job_id)
        return self.jobs[job_id]

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self.jobs.get(job_id)

    def require_job(self, job_id: str) -> Dict[str, Any]:
        return self.jobs[job_id]

    def update_job(self, job_id: str, **changes: Any) -> Dict[str, Any]:
        job = self.require_job(job_id)
        job.update(changes)
        self.persist_job(job_id)
        return job

    def persist_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if job is None:
            return
        self.job_store.save_job(job_id, job)

    def ensure_log_queue(self, job_id: str) -> "queue.Queue[str]":
        if job_id not in self.logs:
            self.logs[job_id] = queue.Queue()
        return self.logs[job_id]

    def has_log_queue(self, job_id: str) -> bool:
        return job_id in self.logs

    def get_log_queue(self, job_id: str) -> Optional["queue.Queue[str]"]:
        return self.logs.get(job_id)

    def append_log_line(self, job_id: str, line: str) -> None:
        self.ensure_log_queue(job_id).put(line + "\n")
        self.job_store.append_log(job_id, line)

    def read_persisted_logs(self, job_id: str):
        return self.job_store.read_logs(job_id)
