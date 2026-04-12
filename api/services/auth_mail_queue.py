from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from api.integrations.queue.redis import RedisQueue
from api.services.auth_mailer import AuthMailDelivery


SEND_VERIFICATION_TASK = "api.tasks.auth_mail_tasks.send_verification_email_task"
SEND_PASSWORD_RESET_TASK = "api.tasks.auth_mail_tasks.send_password_reset_email_task"


class QueueBackend(Protocol):
    def enqueue(self, task_name: str, payload: dict[str, object]) -> dict[str, object]: ...


class AuthMailQueuePublisher(Protocol):
    def enqueue_verification_email(
        self,
        *,
        user_id: str,
        email: str,
        nickname: str,
        code: str,
    ) -> None: ...

    def enqueue_password_reset_email(
        self,
        *,
        user_id: str,
        email: str,
        nickname: str,
        reset_url: str,
    ) -> None: ...


class RqAuthMailQueuePublisher:
    def __init__(self, queue_backend: QueueBackend | None = None) -> None:
        self._queue_backend = queue_backend

    def enqueue_verification_email(
        self,
        *,
        user_id: str,
        email: str,
        nickname: str,
        code: str,
    ) -> None:
        delivery = AuthMailDelivery(
            kind="email_verification",
            user_id=user_id,
            email=email,
            nickname=nickname,
            code=code,
        )
        self._backend.enqueue(
            SEND_VERIFICATION_TASK,
            {"delivery": _serialize_delivery(delivery)},
        )

    def enqueue_password_reset_email(
        self,
        *,
        user_id: str,
        email: str,
        nickname: str,
        reset_url: str,
    ) -> None:
        delivery = AuthMailDelivery(
            kind="password_reset",
            user_id=user_id,
            email=email,
            nickname=nickname,
            reset_url=reset_url,
        )
        self._backend.enqueue(
            SEND_PASSWORD_RESET_TASK,
            {"delivery": _serialize_delivery(delivery)},
        )

    @property
    def _backend(self) -> QueueBackend:
        if self._queue_backend is None:
            self._queue_backend = RedisQueue()
        return self._queue_backend


@lru_cache
def get_auth_mail_queue_publisher() -> AuthMailQueuePublisher:
    return RqAuthMailQueuePublisher()


def _serialize_delivery(delivery: AuthMailDelivery) -> dict[str, object]:
    return {
        "kind": delivery.kind,
        "user_id": delivery.user_id,
        "email": delivery.email,
        "nickname": delivery.nickname,
        "code": delivery.code,
        "reset_url": delivery.reset_url,
    }
