from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock

from api.common.exceptions import ConfigurationError, TooManyRequestsError
from api.core.config import settings

try:  # pragma: no cover - exercised through factory fallback
    from redis import Redis, RedisError
except ImportError:  # pragma: no cover - local dev may not have redis extras installed yet
    Redis = None
    RedisError = Exception


logger = logging.getLogger(__name__)

RATE_LIMIT_MESSAGE = "请求过于频繁，请稍后再试。"


@dataclass(frozen=True, slots=True)
class LLMRateLimitRule:
    limit: int
    window_seconds: int


class LLMRateLimiter:
    """LLM 调用路径的滑动窗口限流器。

    进程内实现使用精确时间戳队列；生产环境应通过 Redis 实现
    跨进程共享计数。两者对同一 (action, owner) 的语义一致。
    """

    def __init__(
        self,
        *,
        rules: dict[str, LLMRateLimitRule] | None = None,
        now_fn=time.monotonic,
    ) -> None:
        self._rules = rules
        self._now_fn = now_fn

    def consume(self, *, action: str, key: str) -> None:
        raise NotImplementedError


class InMemoryLLMRateLimiter(LLMRateLimiter):
    def __init__(
        self,
        *,
        rules: dict[str, LLMRateLimitRule] | None = None,
        now_fn=time.monotonic,
    ) -> None:
        super().__init__(rules=rules, now_fn=now_fn)
        self._attempts: dict[str, list[float]] = {}
        self._lock = Lock()

    def _resolve_rule(self, action: str) -> LLMRateLimitRule:
        if self._rules is not None:
            return self._rules[action]
        return default_llm_rate_limit_rule(action)

    def consume(self, *, action: str, key: str) -> None:
        rule = self._resolve_rule(action)
        now = self._now_fn()
        bucket_key = f"llm:{action}:{key}"
        cutoff = now - rule.window_seconds
        with self._lock:
            attempts = self._attempts.setdefault(bucket_key, [])
            self._attempts[bucket_key] = [ts for ts in attempts if ts > cutoff]
            attempts = self._attempts[bucket_key]
            if len(attempts) >= rule.limit:
                raise TooManyRequestsError(RATE_LIMIT_MESSAGE)
            attempts.append(now)


class RedisLLMRateLimiter(LLMRateLimiter):
    def __init__(
        self,
        client,
        *,
        rules: dict[str, LLMRateLimitRule] | None = None,
        now_fn=time.time,
    ) -> None:
        super().__init__(rules=rules, now_fn=now_fn)
        self._client = client
        # Redis 故障时降级为进程内计数，护栏不应成为主路径的单点故障。
        self._fallback = InMemoryLLMRateLimiter(rules=rules, now_fn=now_fn)

    def _resolve_rule(self, action: str) -> LLMRateLimitRule:
        if self._rules is not None:
            return self._rules[action]
        return default_llm_rate_limit_rule(action)

    def consume(self, *, action: str, key: str) -> None:
        """固定窗口计数限流：INCR + 首次设置过期，保证原子窗口生命周期。"""
        rule = self._resolve_rule(action)
        redis_key = f"llm:rate:{action}:{key}:{int(self._now_fn() // rule.window_seconds)}"
        try:
            current = self._client.incr(redis_key)
        except RedisError:
            logger.warning("llm_rate_limit_redis_unavailable action=%s key=%s", action, key)
            self._fallback.consume(action=action, key=key)
            return
        if current == 1:
            self._client.expire(redis_key, rule.window_seconds)
        if current > rule.limit:
            raise TooManyRequestsError(RATE_LIMIT_MESSAGE)


def default_llm_rate_limit_rule(action: str) -> LLMRateLimitRule:
    """按 action 读取 settings 里的默认限流规则。"""
    if action == "session_start":
        return LLMRateLimitRule(
            settings.llm_session_start_limit,
            settings.llm_session_start_window_seconds,
        )
    if action == "reply":
        return LLMRateLimitRule(
            settings.llm_reply_limit,
            settings.llm_reply_window_seconds,
        )
    raise ConfigurationError(f"Unknown LLM rate limit action: {action}")


@lru_cache
def get_llm_rate_limiter() -> LLMRateLimiter:
    if not settings.redis_url.strip():
        return InMemoryLLMRateLimiter()
    if Redis is None:
        raise ConfigurationError("REDIS_URL is configured but redis dependency is not installed")
    return RedisLLMRateLimiter(Redis.from_url(settings.redis_url, decode_responses=True))
