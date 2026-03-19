from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Any, Callable, Optional, Protocol

from .queue_backend import create_rq_queue


@dataclass(frozen=True)
class JobRunHandle:
    backend: str
    run_id: str
    native_handle: Optional[Any] = None


class JobRunner(Protocol):
    def start(self, target: Callable[..., Any], *args: Any) -> JobRunHandle:
        ...


class ThreadJobRunner:
    backend_name = "thread"

    def start(self, target: Callable[..., Any], *args: Any) -> JobRunHandle:
        thread = threading.Thread(target=target, args=args, daemon=True)
        thread.start()
        return JobRunHandle(
            backend=self.backend_name,
            run_id=thread.name,
            native_handle=thread,
        )


class QueueJobRunner:
    backend_name = "queue"

    def __init__(self, *, redis_url: str, queue_name: str) -> None:
        self.redis_url = redis_url
        self.queue_name = queue_name

    def start(self, target: Callable[..., Any], *args: Any) -> JobRunHandle:
        queue = create_rq_queue(redis_url=self.redis_url, queue_name=self.queue_name)
        job = queue.enqueue(target, *args)
        return JobRunHandle(
            backend=self.backend_name,
            run_id=job.get_id(),
            native_handle=job,
        )


def create_job_runner(backend: str, *, redis_url: str = "", queue_name: str = "default") -> JobRunner:
    normalized = str(backend or "thread").strip().lower()
    if normalized == "thread":
        return ThreadJobRunner()
    if normalized == "queue":
        return QueueJobRunner(redis_url=redis_url, queue_name=queue_name)
    raise ValueError(f"Unsupported job runner backend: {backend}")
