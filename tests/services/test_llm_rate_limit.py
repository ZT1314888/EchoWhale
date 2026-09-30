from __future__ import annotations

import pytest

from api.common.exceptions import ConfigurationError, TooManyRequestsError
from api.core.config import settings
from redis.exceptions import RedisError

from api.services.llm_rate_limit import (
    InMemoryLLMRateLimiter,
    LLMRateLimitRule,
    RedisLLMRateLimiter,
    default_llm_rate_limit_rule,
    get_llm_rate_limiter,
)


class FakeRedis:
    """用字典模拟 INCR/EXPIRE 的最小 Redis 客户端。"""

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def expire(self, key: str, ttl_seconds: int) -> None:
        self.ttls[key] = ttl_seconds


def test_in_memory_limiter_allows_up_to_limit() -> None:
    clock = {"now": 1000.0}
    limiter = InMemoryLLMRateLimiter(
        rules={"reply": LLMRateLimitRule(3, 60)},
        now_fn=lambda: clock["now"],
    )

    for _ in range(3):
        limiter.consume(action="reply", key="owner_1")

    with pytest.raises(TooManyRequestsError):
        limiter.consume(action="reply", key="owner_1")


def test_in_memory_limiter_recovers_after_window_slides() -> None:
    clock = {"now": 1000.0}
    limiter = InMemoryLLMRateLimiter(
        rules={"reply": LLMRateLimitRule(1, 60)},
        now_fn=lambda: clock["now"],
    )

    limiter.consume(action="reply", key="owner_1")
    with pytest.raises(TooManyRequestsError):
        limiter.consume(action="reply", key="owner_1")

    clock["now"] += 61
    limiter.consume(action="reply", key="owner_1")


def test_in_memory_limiter_isolates_keys_and_actions() -> None:
    limiter = InMemoryLLMRateLimiter(
        rules={
            "reply": LLMRateLimitRule(1, 60),
            "session_start": LLMRateLimitRule(1, 60),
        },
        now_fn=lambda: 0.0,
    )

    limiter.consume(action="reply", key="owner_1")
    limiter.consume(action="reply", key="owner_2")
    limiter.consume(action="session_start", key="owner_1")


def test_redis_limiter_counts_per_fixed_window() -> None:
    client = FakeRedis()
    limiter = RedisLLMRateLimiter(
        client,
        rules={"reply": LLMRateLimitRule(2, 60)},
        now_fn=lambda: 1_000_000.0,
    )

    limiter.consume(action="reply", key="owner_1")
    limiter.consume(action="reply", key="owner_1")
    with pytest.raises(TooManyRequestsError):
        limiter.consume(action="reply", key="owner_1")

    window_key = "llm:rate:reply:owner_1:16666"
    assert client.counters[window_key] == 3
    assert client.ttls[window_key] == 60


def test_unknown_action_raises_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        default_llm_rate_limit_rule("unknown_action")


def test_factory_defaults_from_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "redis_url", "")
    limiter = get_llm_rate_limiter()
    assert isinstance(limiter, InMemoryLLMRateLimiter)

    assert default_llm_rate_limit_rule("session_start").limit == settings.llm_session_start_limit
    assert default_llm_rate_limit_rule("reply").limit == settings.llm_reply_limit


class FlakyRedis:
    """incr 一律抛 RedisError 的假客户端，模拟 Redis 故障。"""

    def incr(self, key: str) -> int:
        raise RedisError("connection refused")

    def expire(self, key: str, ttl_seconds: int) -> None:
        raise RedisError("connection refused")


def test_redis_limiter_degrades_to_in_memory_on_redis_failure() -> None:
    limiter = RedisLLMRateLimiter(
        FlakyRedis(),
        rules={"reply": LLMRateLimitRule(limit=1, window_seconds=60)},
        now_fn=lambda: 1000.0,
    )

    # Redis 故障不影响放行判定，退化为进程内计数。
    limiter.consume(action="reply", key="owner_1")
    with pytest.raises(TooManyRequestsError):
        limiter.consume(action="reply", key="owner_1")
