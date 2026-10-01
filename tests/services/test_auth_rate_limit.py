"""AuthRateLimiter 有界性测试：键容量上限 + LRU 淘汰。

注册/登录限流的 key 含邮箱与来源 IP，攻击者可批量伪造请求撑出
无界进程内字典；注入小容量验证最久未用键被淘汰且计数一并消失。
"""

from __future__ import annotations

import pytest

from api.common.exceptions import TooManyRequestsError
from api.services.auth_rate_limit import AuthRateLimitRule, AuthRateLimiter


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
