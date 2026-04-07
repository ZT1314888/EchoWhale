from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock
from time import monotonic

from api.common.exceptions import TooManyRequestsError


@dataclass(frozen=True, slots=True)
class AuthRateLimitRule:
    limit: int
    window_seconds: int
    message: str


DEFAULT_AUTH_RATE_LIMITS: dict[str, AuthRateLimitRule] = {
    "register": AuthRateLimitRule(5, 300, "Too many registration attempts. Please try again later."),
    "login": AuthRateLimitRule(8, 300, "Too many login attempts. Please try again later."),
    "refresh": AuthRateLimitRule(20, 300, "Too many session refresh attempts. Please try again later."),
    "resend_verification": AuthRateLimitRule(
        5,
        300,
        "Too many verification email requests. Please try again later.",
    ),
    "verify_email": AuthRateLimitRule(
        10,
        300,
        "Too many email verification attempts. Please try again later.",
    ),
    "forgot_password": AuthRateLimitRule(
        5,
        300,
        "Too many password reset requests. Please try again later.",
    ),
    "reset_password": AuthRateLimitRule(
        8,
        300,
        "Too many password reset attempts. Please try again later.",
    ),
}


class AuthRateLimiter:
    def __init__(
        self,
        rules: dict[str, AuthRateLimitRule] | None = None,
        *,
        time_fn=monotonic,
    ) -> None:
        self._rules = rules or DEFAULT_AUTH_RATE_LIMITS
        self._time_fn = time_fn
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def consume(self, *, action: str, key: str) -> None:
        rule = self._rules[action]
        now = self._time_fn()
        bucket_key = f"{action}:{key}"
        cutoff = now - rule.window_seconds
        with self._lock:
            attempts = self._attempts[bucket_key]
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= rule.limit:
                raise TooManyRequestsError(rule.message)
            attempts.append(now)

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()


@lru_cache
def get_auth_rate_limiter() -> AuthRateLimiter:
    return AuthRateLimiter()
