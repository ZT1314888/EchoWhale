from __future__ import annotations

import pytest

from api.common.exceptions import TooManyRequestsError, ValidationError
from api.services.email_verification_store import InMemoryEmailVerificationStore


class Clock:
    def __init__(self) -> None:
        self.now = 1_700_000_000.0

    def time(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_issue_and_consume_code_happy_path() -> None:
    clock = Clock()
    store = InMemoryEmailVerificationStore(now_fn=clock.time)

    code = store.issue_code(email="learner@example.com", ip_address="127.0.0.1")

    store.consume_code(email="learner@example.com", code=code)

    with pytest.raises(ValidationError, match="Verification code is invalid or expired"):
        store.consume_code(email="learner@example.com", code=code)


def test_issue_code_enforces_cooldown_per_email_and_ip() -> None:
    clock = Clock()
    store = InMemoryEmailVerificationStore(now_fn=clock.time)

    store.issue_code(email="learner@example.com", ip_address="127.0.0.1")

    with pytest.raises(TooManyRequestsError, match="请求过于频繁"):
        store.issue_code(email="learner@example.com", ip_address="127.0.0.1")


def test_issue_code_enforces_daily_limit_after_cooldown_windows() -> None:
    clock = Clock()
    store = InMemoryEmailVerificationStore(now_fn=clock.time)

    for _ in range(5):
        store.issue_code(email="learner@example.com", ip_address="127.0.0.1")
        clock.advance(61)

    with pytest.raises(TooManyRequestsError, match="请求过于频繁"):
        store.issue_code(email="learner@example.com", ip_address="127.0.0.1")
