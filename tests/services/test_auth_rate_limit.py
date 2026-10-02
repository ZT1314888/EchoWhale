"""AuthRateLimiter 有界性测试：键容量上限 + LRU 淘汰。

注册/登录限流的 key 含邮箱与来源 IP，攻击者可批量伪造请求撑出
无界进程内字典；注入小容量验证最久未用键被淘汰且计数一并消失。
"""

from __future__ import annotations

import logging

import pytest
from redis.exceptions import RedisError

from api.common.exceptions import TooManyRequestsError
from api.core.config import settings
from api.services.auth_rate_limit import (
    AuthRateLimiter,
    AuthRateLimitRule,
    RedisAuthRateLimiter,
    get_auth_rate_limiter,
)


def _limiter(max_keys: int) -> AuthRateLimiter:
    return AuthRateLimiter(
        rules={"login": AuthRateLimitRule(limit=2, window_seconds=60, message="too many")},
        max_keys=max_keys,
    )


def test_auth_limiter_allows_up_to_limit() -> None:
    limiter = _limiter(max_keys=10)

    limiter.consume(action="login", key="alice")
    limiter.consume(action="login", key="alice")
    with pytest.raises(TooManyRequestsError):
        limiter.consume(action="login", key="alice")


def test_auth_limiter_evicts_least_recently_used_keys_beyond_capacity() -> None:
    limiter = _limiter(max_keys=3)

    # alice 打满（两次），随后 bob / carol / dave 依次入库触发淘汰。
    limiter.consume(action="login", key="alice")
    limiter.consume(action="login", key="alice")
    limiter.consume(action="login", key="bob")
    limiter.consume(action="login", key="carol")
    limiter.consume(action="login", key="dave")

    # 最久未用的 alice 被淘汰，字典大小恒等于容量上限。
    assert len(limiter._attempts) == 3
    assert "login:alice" not in limiter._attempts

    # 被淘汰键的计数一并消失：alice 重新进来按全新窗口重新计数
    # （限额 2：两次放行、第三次拒绝），不会残留旧额度。
    limiter.consume(action="login", key="alice")
    limiter.consume(action="login", key="alice")
    with pytest.raises(TooManyRequestsError):
        limiter.consume(action="login", key="alice")


def test_auth_limiter_keeps_active_keys_hot_for_eviction() -> None:
    limiter = _limiter(max_keys=2)

    # hot 打满（限额 2），随后持续被访问（即使每次都被拒绝）。
    limiter.consume(action="login", key="hot")
    limiter.consume(action="login", key="hot")
    with pytest.raises(TooManyRequestsError):
        limiter.consume(action="login", key="hot")
    limiter.consume(action="login", key="cold_1")
    # hot 再次被访问：刷新"最近使用"位置，cold_2 触发淘汰时
    # 牺牲的是更久未用的 cold_1 而不是 hot。
    with pytest.raises(TooManyRequestsError):
        limiter.consume(action="login", key="hot")
    limiter.consume(action="login", key="cold_2")

    assert "login:hot" in limiter._attempts
    assert "login:cold_1" not in limiter._attempts
    # hot 的计数未被淘汰重置：仍处于打满状态。
    with pytest.raises(TooManyRequestsError):
        limiter.consume(action="login", key="hot")


def test_auth_limiter_reset_clears_all_buckets() -> None:
    limiter = _limiter(max_keys=10)

    limiter.consume(action="login", key="alice")
    limiter.reset()

    assert len(limiter._attempts) == 0
    # 清空后重新计数，不会残留旧额度。
    limiter.consume(action="login", key="alice")
    limiter.consume(action="login", key="alice")
    with pytest.raises(TooManyRequestsError):
        limiter.consume(action="login", key="alice")


def test_auth_limiter_tolerates_zero_capacity_misconfiguration() -> None:
    """max_keys 误配成 0/负数：应退化为最小容量而非 popitem 的 KeyError 打崩登录链路。"""
    limiter = AuthRateLimiter(
        rules={"login": AuthRateLimitRule(limit=5, window_seconds=60, message="too many")},
        max_keys=0,
    )

    # 每个新键挤掉前一个键，字典大小恒有界且全程不抛异常。
    limiter.consume(action="login", key="alice")
    limiter.consume(action="login", key="bob")
    assert len(limiter._attempts) == 1
    assert "login:bob" in limiter._attempts

    # 现存键继续正常计数（限额 5 内放行）。
    limiter.consume(action="login", key="bob")
    assert len(limiter._attempts["login:bob"]) == 2


class FakeRedis:
    """用字典模拟 INCR/EXPIRE 的最小 Redis 客户端（与 test_llm_rate_limit 同形）。"""

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def expire(self, key: str, ttl_seconds: int) -> None:
        self.ttls[key] = ttl_seconds


class FlakyRedis:
    """incr 一律抛 RedisError 的假客户端，模拟 Redis 故障。"""

    def incr(self, key: str) -> int:
        raise RedisError("connection refused")

    def expire(self, key: str, ttl_seconds: int) -> None:
        raise RedisError("connection refused")


def test_redis_auth_limiter_shares_counts_across_instances() -> None:
    """多实例（多 worker 的替身）用同一 Redis 时必须共享计数，配额不按进程数倍增。"""
    client = FakeRedis()
    rule = AuthRateLimitRule(limit=2, window_seconds=60, message="too many")
    limiter_a = RedisAuthRateLimiter(client, rules={"login": rule}, time_fn=lambda: 1000.0)
    limiter_b = RedisAuthRateLimiter(client, rules={"login": rule}, time_fn=lambda: 1000.0)

    limiter_a.consume(action="login", key="alice")
    limiter_b.consume(action="login", key="alice")
    with pytest.raises(TooManyRequestsError) as excinfo:
        limiter_b.consume(action="login", key="alice")

    # 每 action 独立文案在 Redis 变体上不丢失。
    assert excinfo.value.message == "too many"
    window_key = "auth:rate:login:alice:16"
    assert client.counters[window_key] == 3
    assert client.ttls[window_key] == 60


def test_redis_auth_limiter_resets_after_window_renews() -> None:
    """窗口翻新后计数归零：新窗口按全新配额放行。"""
    client = FakeRedis()
    clock = {"now": 1000.0}
    limiter = RedisAuthRateLimiter(
        client,
        rules={"login": AuthRateLimitRule(limit=1, window_seconds=60, message="too many")},
        time_fn=lambda: clock["now"],
    )

    limiter.consume(action="login", key="alice")
    with pytest.raises(TooManyRequestsError):
        limiter.consume(action="login", key="alice")

    clock["now"] += 60
    limiter.consume(action="login", key="alice")
    assert client.counters["auth:rate:login:alice:17"] == 1


def test_redis_auth_limiter_degrades_to_in_memory_on_redis_failure(caplog) -> None:
    """Redis 故障不影响放行判定：退化为进程内计数并记 warning。"""
    limiter = RedisAuthRateLimiter(
        FlakyRedis(),
        rules={"login": AuthRateLimitRule(limit=1, window_seconds=60, message="too many")},
        time_fn=lambda: 1000.0,
    )

    with caplog.at_level(logging.WARNING, logger="api.services.auth_rate_limit"):
        limiter.consume(action="login", key="alice")
        with pytest.raises(TooManyRequestsError):
            limiter.consume(action="login", key="alice")

    assert "auth_rate_limit_redis_unavailable" in caplog.text


def test_factory_uses_in_memory_without_redis_url(monkeypatch) -> None:
    """工厂口径与 get_llm_rate_limiter 一致：未配置 redis_url 时用进程内实现。"""
    monkeypatch.setattr(settings, "redis_url", "")
    get_auth_rate_limiter.cache_clear()
    try:
        assert type(get_auth_rate_limiter()) is AuthRateLimiter
    finally:
        get_auth_rate_limiter.cache_clear()


def test_factory_builds_redis_limiter_when_configured(monkeypatch) -> None:
    """配置了 redis_url 时构建 Redis 实现（客户端惰性连接，构造不触网）。"""
    monkeypatch.setattr(settings, "redis_url", "redis://localhost:6379/0")
    get_auth_rate_limiter.cache_clear()
    try:
        limiter = get_auth_rate_limiter()
        assert isinstance(limiter, RedisAuthRateLimiter)
    finally:
        get_auth_rate_limiter.cache_clear()
