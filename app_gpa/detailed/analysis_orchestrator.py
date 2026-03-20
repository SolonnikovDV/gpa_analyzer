from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from .job_contracts import (
    JOB_STATUS_DONE,
    JOB_STATUS_ERROR,
    JOB_STATUS_RUNNING,
    JOB_STATUS_TABLES_DISCOVERED,
)
from .job_service import JobService


class AnalysisOrchestrator:
    def __init__(
        self,
        job_service: JobService,
        performance_monitors: Dict[str, Any],
        performance_monitor_factory: Callable[[], Any],
    ) -> None:
        self.job_service = job_service
        self.performance_monitors = performance_monitors
        self.performance_monitor_factory = performance_monitor_factory

    def create_discovery_job(self, job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.job_service.create_job(job_id, payload)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self.job_service.get_job(job_id)

    def require_job(self, job_id: str) -> Dict[str, Any]:
        return self.job_service.require_job(job_id)

    def set_discovery_result(self, job_id: str, analyzer: Any, result: Dict[str, Any]) -> Dict[str, Any]:
        job = self.require_job(job_id)
        job["analyzer"] = analyzer
        job["discovery_result"] = result
        job["status"] = JOB_STATUS_TABLES_DISCOVERED
        self.job_service.persist_job(job_id)
        return job

    def store_analysis_params(self, job_id: str, params: Any) -> Dict[str, Any]:
        job = self.require_job(job_id)
        job["saved_params"] = params
        if job.get("discovery_result"):
            job["discovery_result"]["user_params"] = params
        self.job_service.persist_job(job_id)
        return job

    def prepare_analysis_run(
        self,
        job_id: str,
        credentials_resolver: Callable[[], Any],
        scope_resolver: Callable[[], Any],
    ) -> Dict[str, Any]:
        job = self.require_job(job_id)
        job["status"] = JOB_STATUS_RUNNING
        job["agent_credentials"] = job.get("agent_credentials") or credentials_resolver()
        job["agent_scope"] = job.get("agent_scope") or scope_resolver()
        self.job_service.persist_job(job_id)
        return job

    def complete_analysis(self, job_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
        job = self.require_job(job_id)
        job["result"] = result
        job["status"] = JOB_STATUS_DONE
        self.job_service.persist_job(job_id)
        return job

    def fail_job(self, job_id: str, error: str) -> Dict[str, Any]:
        job = self.require_job(job_id)
        job["status"] = JOB_STATUS_ERROR
        job["error"] = error
        self.job_service.persist_job(job_id)
        return job

    def start_performance_monitor(self, job_id: str) -> Any:
        monitor = self.performance_monitor_factory()
        monitor.start_monitoring()
        self.performance_monitors[job_id] = monitor
        return monitor
