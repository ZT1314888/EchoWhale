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


def test_in_memory_limiter_evicts_least_recently_used_keys_beyond_capacity() -> None:
    """容量上限有界性：visitor_id 可被客户端无限轮换，进程内字典必须可淘汰。"""
    clock = {"now": 1000.0}
    limiter = InMemoryLLMRateLimiter(
        rules={"reply": LLMRateLimitRule(limit=2, window_seconds=60)},
        now_fn=lambda: clock["now"],
        max_keys=3,
    )

    # key_1 打满（两次），随后 key_2 / key_3 / key_4 依次入库触发淘汰。
    limiter.consume(action="reply", key="key_1")
    limiter.consume(action="reply", key="key_1")
    limiter.consume(action="reply", key="key_2")
    limiter.consume(action="reply", key="key_3")
    limiter.consume(action="reply", key="key_4")

    # 最久未用的 key_1 被淘汰，字典大小恒等于容量上限。
    assert len(limiter._attempts) == 3
    assert "llm:reply:key_1" not in limiter._attempts

    # 被淘汰键的计数一并消失：key_1 重新进来按全新窗口重新计数
    # （限额 2：两次放行、第三次拒绝），不会残留旧额度。
    limiter.consume(action="reply", key="key_1")
    limiter.consume(action="reply", key="key_1")
    with pytest.raises(TooManyRequestsError):
        limiter.consume(action="reply", key="key_1")


def test_in_memory_limiter_keeps_active_keys_hot_for_eviction() -> None:
    """命中（含被拒绝）都算使用：持续活跃的键不应被淘汰重置计数。"""
    clock = {"now": 1000.0}
    limiter = InMemoryLLMRateLimiter(
        rules={"reply": LLMRateLimitRule(limit=1, window_seconds=60)},
        now_fn=lambda: clock["now"],
        max_keys=2,
    )

    limiter.consume(action="reply", key="hot_key")
    with pytest.raises(TooManyRequestsError):
        limiter.consume(action="reply", key="hot_key")
    limiter.consume(action="reply", key="cold_1")
    # hot_key 再次被访问（即使仍会被拒绝）：刷新其"最近使用"位置，
    # 使随后的新键 cold_2 淘汰的是更久未用的 cold_1 而不是 hot_key。
    with pytest.raises(TooManyRequestsError):
        limiter.consume(action="reply", key="hot_key")
    limiter.consume(action="reply", key="cold_2")

    assert "llm:reply:hot_key" in limiter._attempts
    assert "llm:reply:cold_1" not in limiter._attempts
    # hot_key 的计数未被重置：仍处于打满状态。
    with pytest.raises(TooManyRequestsError):
        limiter.consume(action="reply", key="hot_key")


def test_in_memory_limiter_tolerates_zero_capacity_misconfiguration() -> None:
    """max_keys 误配成 0/负数：应退化为最小容量而非 popitem 的 KeyError 打崩请求。"""
    limiter = InMemoryLLMRateLimiter(
        rules={"reply": LLMRateLimitRule(limit=5, window_seconds=60)},
        max_keys=0,
    )

    # 每个新键挤掉前一个键，字典大小恒有界且全程不抛异常。
    limiter.consume(action="reply", key="key_1")
    limiter.consume(action="reply", key="key_2")
    limiter.consume(action="reply", key="key_3")
    assert len(limiter._attempts) == 1
    assert "llm:reply:key_3" in limiter._attempts

    # 现存键继续正常计数（限额 5 内放行）。
    limiter.consume(action="reply", key="key_3")
    assert limiter._attempts["llm:reply:key_3"]
