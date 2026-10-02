from __future__ import annotations

import logging
from collections import OrderedDict, deque
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock
from time import monotonic, time

from api.common.exceptions import ConfigurationError, TooManyRequestsError
from api.core.config import settings

try:  # pragma: no cover - exercised through factory fallback
    from redis import Redis, RedisError
except ImportError:  # pragma: no cover - local dev may not have redis extras installed yet
    Redis = None
    RedisError = Exception


logger = logging.getLogger(__name__)


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


class RedisAuthRateLimiter(AuthRateLimiter):
    """Redis 固定窗口限流：多 worker / 多实例共享计数，Redis 故障降级进程内。

    与 RedisLLMRateLimiter 同构（INCR + 首次 EXPIRE 的固定窗口），
    但保留每 action 独立超限文案（注册/登录的提示语不同）。
    """

    def __init__(
        self,
        client,
        *,
        rules: dict[str, AuthRateLimitRule] | None = None,
        time_fn=time,
        max_keys: int = 10_000,
    ) -> None:
        super().__init__(rules=rules, time_fn=time_fn, max_keys=max_keys)
        self._client = client
        # Redis 故障时降级为进程内计数（同规则同容量）：
        # 限流护栏不应成为注册/登录主路径的单点故障。
        self._fallback = AuthRateLimiter(rules=rules, time_fn=time_fn, max_keys=max_keys)

    def consume(self, *, action: str, key: str) -> None:
        """固定窗口计数：INCR + 首次设置过期，保证原子窗口生命周期。"""
        rule = self._rules[action]
        redis_key = f"auth:rate:{action}:{key}:{int(self._time_fn() // rule.window_seconds)}"
        try:
            current = self._client.incr(redis_key)
        except RedisError:
            logger.warning("auth_rate_limit_redis_unavailable action=%s key=%s", action, key)
            self._fallback.consume(action=action, key=key)
            return
        if current == 1:
            self._client.expire(redis_key, rule.window_seconds)
        if current > rule.limit:
            raise TooManyRequestsError(rule.message)

    def reset(self) -> None:
        # Redis 键自带 TTL 自然过期，无需显式清理；reset 语义只作用于降级侧计数。
        self._fallback.reset()


@lru_cache
def get_auth_rate_limiter() -> AuthRateLimiter:
    """工厂分流与 get_llm_rate_limiter 口径一致：
    未配置 redis_url → 进程内实现；配置了但 redis 未安装 → 启动期报错；
    否则 Redis 实现（多 worker 下配额不再按进程数倍增）。
    """
    if not settings.redis_url.strip():
        return AuthRateLimiter(max_keys=settings.rate_limiter_max_keys)
    if Redis is None:
        raise ConfigurationError("REDIS_URL is configured but redis dependency is not installed")
    return RedisAuthRateLimiter(
        Redis.from_url(settings.redis_url, decode_responses=True),
        max_keys=settings.rate_limiter_max_keys,
    )
