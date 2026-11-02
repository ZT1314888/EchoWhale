from __future__ import annotations

import pytest

from api.services.auth_mailer import AuthMailDelivery


class FakeQueueBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def enqueue(self, task_name: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append((task_name, payload))
        return {"task_name": task_name, "payload": payload, "status": "queued"}


def test_auth_mail_queue_publisher_enqueues_verification_email_job() -> None:
    from api.services.auth_mail_queue import RqAuthMailQueuePublisher

    backend = FakeQueueBackend()
    publisher = RqAuthMailQueuePublisher(queue_backend=backend)

    publisher.enqueue_verification_email(
        user_id="user_123",
        email="learner@example.com",
        nickname="Echo Learner",
        code="123456",
    )

    assert backend.calls == [
        (
            "api.tasks.auth_mail_tasks.send_verification_email_task",
            {
                "delivery": {
                    "kind": "email_verification",
                    "user_id": "user_123",
                    "email": "learner@example.com",
                    "nickname": "Echo Learner",
                    "code": "123456",
                    "reset_url": None,
                }
            },
        )
    ]


def test_auth_mail_queue_publisher_delays_backend_creation_until_enqueue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.services.auth_mail_queue import RqAuthMailQueuePublisher

    constructed = False

    class FakeRedisQueue:
        def __init__(self) -> None:
            nonlocal constructed
            constructed = True

        def enqueue(self, task_name: str, payload: dict[str, object]) -> dict[str, object]:
            return {"task_name": task_name, "payload": payload, "status": "queued"}

    monkeypatch.setattr("api.services.auth_mail_queue.RedisQueue", FakeRedisQueue)

    RqAuthMailQueuePublisher()

    assert constructed is False


def test_auth_mail_queue_publisher_enqueues_password_reset_job() -> None:
    from api.services.auth_mail_queue import RqAuthMailQueuePublisher

    backend = FakeQueueBackend()
    publisher = RqAuthMailQueuePublisher(queue_backend=backend)

    publisher.enqueue_password_reset_email(
        user_id="user_123",
        email="learner@example.com",
        nickname="Echo Learner",
        reset_url="https://app.example.com/reset-password?token=abc",
    )

    assert backend.calls == [
        (
            "api.tasks.auth_mail_tasks.send_password_reset_email_task",
            {
                "delivery": {
                    "kind": "password_reset",
                    "user_id": "user_123",
                    "email": "learner@example.com",
                    "nickname": "Echo Learner",
                    "code": None,
                    "reset_url": "https://app.example.com/reset-password?token=abc",
                }
            },
        )
    ]


def test_send_verification_email_task_uses_smtp_mailer(monkeypatch: pytest.MonkeyPatch) -> None:
    from api.tasks.auth_mail_tasks import send_verification_email_task

    deliveries: list[AuthMailDelivery] = []

    class FakeSmtpAuthMailer:
        def send_verification_email(self, *, user, code: str) -> None:
            deliveries.append(
                AuthMailDelivery(
                    kind="email_verification",
                    user_id=user.id,
                    email=user.email,
                    code=code,
                )
            )

    monkeypatch.setattr("api.tasks.auth_mail_tasks.SmtpAuthMailer", FakeSmtpAuthMailer)

    send_verification_email_task(
        delivery={
            "kind": "email_verification",
            "user_id": "user_123",
            "email": "learner@example.com",
            "nickname": "Echo Learner",
            "code": "123456",
            "reset_url": None,
        }
    )

    assert deliveries == [
        AuthMailDelivery(
            kind="email_verification",
            user_id="user_123",
            email="learner@example.com",
            code="123456",
        )
    ]


def test_send_password_reset_email_task_uses_smtp_mailer(monkeypatch: pytest.MonkeyPatch) -> None:
    from api.tasks.auth_mail_tasks import send_password_reset_email_task

    deliveries: list[AuthMailDelivery] = []

    class FakeSmtpAuthMailer:
        def send_password_reset_email(self, *, user, reset_url: str) -> None:
            deliveries.append(
                AuthMailDelivery(
                    kind="password_reset",
                    user_id=user.id,
                    email=user.email,
                    reset_url=reset_url,
                )
            )

    monkeypatch.setattr("api.tasks.auth_mail_tasks.SmtpAuthMailer", FakeSmtpAuthMailer)

    send_password_reset_email_task(
        delivery={
            "kind": "password_reset",
            "user_id": "user_123",
            "email": "learner@example.com",
            "nickname": "Echo Learner",
            "code": None,
            "reset_url": "https://app.example.com/reset-password?token=abc",
        }
    )

    assert deliveries == [
        AuthMailDelivery(
            kind="password_reset",
            user_id="user_123",
            email="learner@example.com",
            reset_url="https://app.example.com/reset-password?token=abc",
        )
    ]
