from __future__ import annotations

from typing import Any


def create_redis_connection(redis_url: str) -> Any:
    from redis import Redis

    return Redis.from_url(redis_url)


def create_rq_queue(*, redis_url: str, queue_name: str):
    from rq import Queue

    connection = create_redis_connection(redis_url)
    return Queue(name=queue_name, connection=connection)
