from __future__ import annotations

from core.compat import install_compat_imports

install_compat_imports()

from core.settings import settings
from infrastructure import create_redis_connection


def main() -> None:
    from rq import Connection, Worker

    connection = create_redis_connection(settings.redis_url)
    with Connection(connection):
        worker = Worker([settings.job_queue_name])
        worker.work()


if __name__ == "__main__":
    main()
