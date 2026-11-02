from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

import httpx

from api.common.exceptions import ConfigurationError, EchoWhaleError, ModelProviderError
from api.common.telemetry import (
    ATTR_ATTEMPT_NAME,
    ATTR_RETRY_INDEX,
    ATTR_TERMINAL,
    TERMINAL_OK,
    mark_failed,
    stamp_request_context,
    tracer,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class LLMAttempt(Generic[T]):
    """一次可尝试的 provider 调用，name 用于日志与失败归因。"""

    name: str
    call: Callable[[], Awaitable[T]]


def is_retryable_llm_error(exc: Exception) -> bool:
    """判断错误是否值得在同一 provider 上重试。

    网络/超时/网关类瞬时错误与模型输出解析失败可重试；
    ConfigurationError 属于配置错误，重试无意义。
    """
    if isinstance(exc, ConfigurationError):
        return False
    if isinstance(exc, httpx.TimeoutException | httpx.TransportError):
        return True
    return isinstance(exc, ModelProviderError | ValueError)


async def run_llm_with_failover(
    attempts: Sequence[LLMAttempt[T]],
    *,
    retries_per_provider: int = 1,
    retry_backoff_seconds: float = 0.5,
    deadline_seconds: float | None = None,
    compose_failure: Callable[[list[tuple[str, Exception]]], Exception] | None = None,
) -> T:
    """按顺序尝试每个 provider：瞬时错误先带退避重试，再切换下一个。

    - 单个 provider 内最多重试 retries_per_provider 次（仅针对可重试错误）。
    - deadline_seconds 限制整条调用链的总预算，超时后不再发起后续尝试。
    - 全部失败时优先原样抛出最后一次 EchoWhaleError，其余异常包装为
      ModelProviderError；调用方也可通过 compose_failure 自定义归并策略。
    - 每次 attempt（含重试）打一个 `llm.attempt` span（failover 即 span 序列）：
      属性含 attempt 名、重试序号、request-id 与终态；退避 sleep 在 span 之外，
      span 只覆盖真实调用，backoff 不计入 attempt 耗时（design 2.4）。
    """
    if not attempts:
        raise ConfigurationError("No LLM attempts configured")

    deadline = time.monotonic() + deadline_seconds if deadline_seconds else None
    failures: list[tuple[str, Exception]] = []

    for attempt in attempts:
        if deadline is not None and time.monotonic() >= deadline:
            break
        for retry_index in range(retries_per_provider + 1):
            started = time.monotonic()
            backoff_seconds: float | None = None
            succeeded = False
            result: T | None = None
            with tracer().start_as_current_span(
                "llm.attempt",
                attributes={
                    ATTR_ATTEMPT_NAME: attempt.name,
                    ATTR_RETRY_INDEX: retry_index,
                },
                record_exception=False,
                set_status_on_exception=False,
            ) as span:
                stamp_request_context(span)
                try:
                    result = await attempt.call()
                    succeeded = True
                except ConfigurationError as exc:
                    # 配置错误换 provider 或重试都无法恢复：先记账再原样上抛。
                    mark_failed(span, exc)
                    raise
                except Exception as exc:  # noqa: BLE001 - 主备切换需要兜住任意 provider 失败并记录
                    elapsed = time.monotonic() - started
                    failures.append((attempt.name, exc))
                    logger.warning(
                        "llm_attempt_failed attempt=%s retry=%d/%d elapsed=%.2fs error=%s: %s",
                        attempt.name,
                        retry_index,
                        retries_per_provider,
                        elapsed,
                        type(exc).__name__,
                        exc,
                    )
                    mark_failed(span, exc)
                    # 以下判定与原实现逐条等价：不可重试 → break；deadline 到 →
                    # break；重试余量 → 记下退避时长，sleep 移到 span 外执行；
                    # 重试耗尽 → 落空进入下一轮 attempt。
                    if not is_retryable_llm_error(exc):
                        break
                    if deadline is not None and time.monotonic() >= deadline:
                        break
                    if retry_index < retries_per_provider:
                        backoff_seconds = retry_backoff_seconds * (retry_index + 1)
                except BaseException as exc:
                    # CancelledError 等 BaseException 不吞：记 failed 后原样上抛，
                    # 取消语义保持不变（quality-guidelines：只许 re-raise）。
                    mark_failed(span, exc)
                    raise
                if succeeded:
                    span.set_attribute(ATTR_TERMINAL, TERMINAL_OK)
                    return result
            # 退避 sleep 在 attempt span 之外：span 只覆盖真实调用，backoff 不计入
            # attempt 耗时（design 2.4）；sleep 语义与原实现一致（仅在重试余量内）。
            if backoff_seconds is not None:
                await asyncio.sleep(backoff_seconds)

    if not failures:
        raise ModelProviderError(
            f"LLM deadline exhausted before any attempt completed (deadline={deadline_seconds}s)"
        )
    if compose_failure is not None:
        raise compose_failure(failures) from failures[-1][1]
    last_error = failures[-1][1]
    if isinstance(last_error, EchoWhaleError):
        raise last_error
    raise ModelProviderError(f"All LLM attempts failed: {last_error}") from last_error
