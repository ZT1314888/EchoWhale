from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock
from time import monotonic

from api.common.exceptions import TooManyRequestsError
from api.core.config import settings


@dataclass(frozen=True, slots=True)
class AuthRateLimitRule:
    limit: int
    window_seconds: int
    message: str


DEFAULT_AUTH_RATE_LIMITS: dict[str, AuthRateLimitRule] = {
    "register": AuthRateLimitRule(
        5, 300, "Too many registration attempts. Please try again later."
    ),
    "login": AuthRateLimitRule(8, 300, "Too many login attempts. Please try again later."),
    "refresh": AuthRateLimitRule(
        20, 300, "Too many session refresh attempts. Please try again later."
    ),
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
        max_keys: int = 10_000,
    ) -> None:
        self._rules = rules or DEFAULT_AUTH_RATE_LIMITS
        self._time_fn = time_fn
        # OrderedDict + 容量上限：注册/登录的 key 含邮箱与 IP，攻击者可批量
        # 伪造请求撑出无界字典，最久未用键按 LRU 淘汰保证进程内存有界。
        self._attempts: OrderedDict[str, deque[float]] = OrderedDict()
        self._max_keys = max_keys
        self._lock = Lock()

    def consume(self, *, action: str, key: str) -> None:
        rule = self._rules[action]
        now = self._time_fn()
        bucket_key = f"{action}:{key}"
        cutoff = now - rule.window_seconds
        with self._lock:
            attempts = self._attempts.get(bucket_key)
            if attempts is not None:
                # 命中（含被拒绝）都算一次使用：移到队尾再清理过期时间戳。
                self._attempts.move_to_end(bucket_key)
            else:
                # 原 defaultdict 在 consume 时隐式建键；改为显式建键，
                # 让容量淘汰发生在插入之前，字典大小才真正有界。
                # 空字典不淘汰：max_keys 被误配成 0/负数时退化为最小容量，
                # 而不是 popitem 抛 KeyError 打崩注册/登录链路。
                if self._attempts and len(self._attempts) >= self._max_keys:
                    self._attempts.popitem(last=False)
                attempts = deque()
                self._attempts[bucket_key] = attempts
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
    return AuthRateLimiter(max_keys=settings.rate_limiter_max_keys)
