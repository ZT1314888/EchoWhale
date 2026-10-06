from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock
from typing import TYPE_CHECKING

from api.common.exceptions import ConfigurationError, TooManyRequestsError
from api.core.config import settings
from api.services.rate_limit_window import FixedWindowCounter

if TYPE_CHECKING:  # 类型标注仅此而已：限流模块运行时不耦合路由依赖层
    from fastapi import Request

    from api.common.deps import ResourceOwnerContext

try:  # pragma: no cover - exercised through factory fallback
    from redis import Redis, RedisError
except ImportError:  # pragma: no cover - local dev may not have redis extras installed yet
    Redis = None
    RedisError = Exception


logger = logging.getLogger(__name__)

RATE_LIMIT_MESSAGE = "请求过于频繁，请稍后再试。"

# 媒体上传限流窗口：复用既有动作的 3600 秒窗口语义，不新增环境配置键
# （limits 本身走 settings.media_upload_limit / media_upload_ip_limit）。
MEDIA_UPLOAD_WINDOW_SECONDS = 3600

# 语音 bootstrap 限流窗口：同复用 3600 秒常量语义，不单独暴露环境配置键
# （limits 走 settings.voice_bootstrap_limit / voice_bootstrap_ip_limit）。
VOICE_BOOTSTRAP_WINDOW_SECONDS = 3600


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
        max_keys: int = 10_000,
    ) -> None:
        super().__init__(rules=rules, now_fn=now_fn)
        # OrderedDict 支持按插入序做 LRU 淘汰：visitor_id 可被客户端无限轮换，
        # 无界字典在匿名流量下就是内存泄漏点，容量上限是硬护栏。
        self._attempts: OrderedDict[str, list[float]] = OrderedDict()
        self._max_keys = max_keys
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
            attempts = self._attempts.get(bucket_key)
            if attempts is not None:
                # 命中（含被拒绝的尝试）都算一次使用：移到队尾，
                # 被打满的活跃键不会被误淘汰后意外重置计数。
                self._attempts.move_to_end(bucket_key)
            elif self._attempts and len(self._attempts) >= self._max_keys:
                # 新键入库前先淘汰最久未用的键，保证字典大小恒有界；
                # 空字典不淘汰：max_keys 被误配成 0/负数时退化为最小容量，
                # 而不是 popitem 抛 KeyError 把所有 LLM 请求打成 500。
                self._attempts.popitem(last=False)
                attempts = []
            else:
                attempts = []
            attempts = [ts for ts in attempts if ts > cutoff]
            if len(attempts) >= rule.limit:
                raise TooManyRequestsError(RATE_LIMIT_MESSAGE)
            attempts.append(now)
            self._attempts[bucket_key] = attempts


class RedisLLMRateLimiter(LLMRateLimiter):
    def __init__(
        self,
        client,
        *,
        rules: dict[str, LLMRateLimitRule] | None = None,
        now_fn=time.time,
        max_keys: int = 10_000,
    ) -> None:
        super().__init__(rules=rules, now_fn=now_fn)
        self._client = client
        # 固定窗口原子计数：INCR 与首次 EXPIRE 在服务端单次 EVAL 完成，
        # 两命令之间崩溃不再留下无 TTL 的永久键；键构造保持不变。
        self._counter = FixedWindowCounter(client)
        # Redis 故障时降级为进程内计数，护栏不应成为主路径的单点故障；
        # 降级路径同样继承容量上限，避免退化后字典无界增长。
        self._fallback = InMemoryLLMRateLimiter(rules=rules, now_fn=now_fn, max_keys=max_keys)

    def _resolve_rule(self, action: str) -> LLMRateLimitRule:
        if self._rules is not None:
            return self._rules[action]
        return default_llm_rate_limit_rule(action)

    def consume(self, *, action: str, key: str) -> None:
        """固定窗口计数限流：INCR + 首次设置过期原子完成，保证窗口生命周期。"""
        rule = self._resolve_rule(action)
        redis_key = f"llm:rate:{action}:{key}:{int(self._now_fn() // rule.window_seconds)}"
        try:
            current = self._counter.increment(redis_key, rule.window_seconds)
        except RedisError:
            logger.warning("llm_rate_limit_redis_unavailable action=%s key=%s", action, key)
            self._fallback.consume(action=action, key=key)
            return
        if current > rule.limit:
            raise TooManyRequestsError(RATE_LIMIT_MESSAGE)


def default_llm_rate_limit_rule(action: str) -> LLMRateLimitRule:
    """按 action 读取 settings 里的默认限流规则。

    *_ip 两个 action 是匿名访客的 IP 维度兜底限额（默认 visitor 限额 ×5）：
    单 IP 轮换 Cookie 刷新配额时，visitor 键挡不住，IP 键兜底；
    共享出口 IP（NAT/公司网络）的误伤由放大系数吸收。
    """
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
    if action == "session_start_ip":
        return LLMRateLimitRule(
            settings.llm_session_start_ip_limit,
            settings.llm_session_start_window_seconds,
        )
    if action == "reply_ip":
        return LLMRateLimitRule(
            settings.llm_reply_ip_limit,
            settings.llm_reply_window_seconds,
        )
    if action == "media_upload":
        return LLMRateLimitRule(
            settings.media_upload_limit,
            MEDIA_UPLOAD_WINDOW_SECONDS,
        )
    if action == "media_upload_ip":
        return LLMRateLimitRule(
            settings.media_upload_ip_limit,
            MEDIA_UPLOAD_WINDOW_SECONDS,
        )
    if action == "voice_bootstrap":
        return LLMRateLimitRule(
            settings.voice_bootstrap_limit,
            VOICE_BOOTSTRAP_WINDOW_SECONDS,
        )
    if action == "voice_bootstrap_ip":
        return LLMRateLimitRule(
            settings.voice_bootstrap_ip_limit,
            VOICE_BOOTSTRAP_WINDOW_SECONDS,
        )
    if action == "think_proxy":
        # Deepgram think 代理按令牌里的 sid 计数：令牌 TTL 内可复用，
        # 会话维度配额是该复用性的主要约束。
        return LLMRateLimitRule(
            settings.think_proxy_limit,
            settings.think_proxy_window_seconds,
        )
    raise ConfigurationError(f"Unknown LLM rate limit action: {action}")


def consume_with_ip_guard(
    limiter: LLMRateLimiter,
    *,
    action: str,
    ip_action: str,
    owner: ResourceOwnerContext,
    request: Request,
) -> None:
    """先消耗 owner（账号/visitor）键，再对匿名访客追加 IP 维度兜底键。

    sessions 与 media/upload 的匿名 IP 守卫是同一模式，抽公共 helper
    供两处复用，避免键顺序与跳过条件在端点间漂移（任务 prd R3 / DRY）。

    IP 键只取 TCP 对端地址（request.client.host），不解析 X-Forwarded-For：
    XFF 头可被客户端随意伪造，用它等于把 IP 键也交给攻击者轮换。
    认证用户不受 IP 键约束（owner 键已按账号归属计数）；
    request.client 为 None（部分测试/UDS 部署）时跳过，避免误伤。
    """
    limiter.consume(action=action, key=owner.owner_id)
    if not owner.is_anonymous:
        return
    if request.client is None:
        return
    limiter.consume(action=ip_action, key=f"ip:{request.client.host}")


@lru_cache
def get_llm_rate_limiter() -> LLMRateLimiter:
    if not settings.redis_url.strip():
        return InMemoryLLMRateLimiter(max_keys=settings.rate_limiter_max_keys)
    if Redis is None:
        raise ConfigurationError("REDIS_URL is configured but redis dependency is not installed")
    return RedisLLMRateLimiter(
        Redis.from_url(settings.redis_url, decode_responses=True),
        max_keys=settings.rate_limiter_max_keys,
    )
