from __future__ import annotations

from functools import lru_cache
import sys
from typing import Any

from api.common.exceptions import ConfigurationError
from api.common.exceptions import QueuePublishError
from api.core.config import settings

try:  # pragma: no cover - exercised through factory fallback
    from redis import Redis
except ImportError:  # pragma: no cover - local dev may not have redis extras installed yet
    Redis = None


def _enable_rq_windows_import_compat() -> None:
    if sys.platform != "win32":
        return

    import multiprocessing.context as mp_context

    if "fork" not in mp_context._concrete_contexts and "spawn" in mp_context._concrete_contexts:
        mp_context._concrete_contexts["fork"] = mp_context._concrete_contexts["spawn"]


try:  # pragma: no cover - exercised through factory fallback
    _enable_rq_windows_import_compat()
    from rq import Queue
    from rq import Retry
except ImportError:  # pragma: no cover - local dev may not have rq installed yet
    Queue = None
    Retry = None
except ValueError:  # pragma: no cover - unsupported platform/runtime mismatch
    Queue = None
    Retry = None


DEFAULT_RETRY_INTERVALS = [10, 30, 60]


class RedisQueue:
    def __init__(
        self,
        *,
        redis_client: Redis | None = None,
        queue_name: str | None = None,
    ) -> None:
        self._redis_client = redis_client or get_queue_redis_client()
        self._queue_name = queue_name or settings.auth_mail_queue_name

    def enqueue(self, task_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if Queue is None or Retry is None:
            raise ConfigurationError("RQ is not installed")

        try:
            queue = Queue(name=self._queue_name, connection=self._redis_client)
            job = queue.enqueue(
                task_name,
                kwargs=payload,
                retry=Retry(max=len(DEFAULT_RETRY_INTERVALS), interval=DEFAULT_RETRY_INTERVALS),
            )
        except ConfigurationError:
            raise
        except Exception as exc:
            raise QueuePublishError() from exc

        return {
            "task_name": task_name,
            "payload": payload,
            "status": "queued",
            "job_id": job.id,
        }


@lru_cache
def get_queue_redis_client() -> Redis:
    if not settings.redis_url.strip():
        raise ConfigurationError("REDIS_URL must be set when auth mail queue is enabled")
    if Redis is None:
        raise ConfigurationError("REDIS_URL is configured but redis dependency is not installed")
    return Redis.from_url(settings.redis_url)
