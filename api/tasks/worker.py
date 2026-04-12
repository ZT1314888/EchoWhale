from __future__ import annotations

from api.common.exceptions import ConfigurationError
from api.core.config import settings
from api.integrations.queue.redis import _enable_rq_windows_import_compat
from api.integrations.queue.redis import get_queue_redis_client

def main() -> None:
    try:  # pragma: no cover - exercised only in runtime worker process
        _enable_rq_windows_import_compat()
        from rq import Worker
    except (ImportError, ValueError) as exc:  # pragma: no cover - runtime only
        raise ConfigurationError("RQ is not installed") from exc

    if Worker is None:
        raise ConfigurationError("RQ is not installed")

    worker = Worker([settings.auth_mail_queue_name], connection=get_queue_redis_client())
    worker.work()


if __name__ == "__main__":
    main()
