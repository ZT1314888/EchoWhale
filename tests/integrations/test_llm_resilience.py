from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from api.common.exceptions import (
    ConfigurationError,
    ModelProviderError,
    UnsupportedSceneImageError,
)
from api.integrations.llm.resilience import (
    LLMAttempt,
    is_retryable_llm_error,
    run_llm_with_failover,
)


class ScriptedCall:
    """按脚本依次抛错的假调用：脚本耗尽后返回固定结果。"""

    def __init__(self, errors: list[Exception], result: str = "ok") -> None:
        self._errors = list(errors)
        self._result = result
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        if self._errors:
            raise self._errors.pop(0)
        return self._result


@pytest.mark.anyio
async def test_returns_first_success_without_retry() -> None:
    primary = ScriptedCall([])

    result = await run_llm_with_failover(
        [LLMAttempt("primary", primary)],
        retries_per_provider=1,
        retry_backoff_seconds=0,
    )

    assert result == "ok"
    assert primary.calls == 1


@pytest.mark.anyio
async def test_retries_same_provider_on_transient_error() -> None:
    primary = ScriptedCall([ModelProviderError("transient")])

    result = await run_llm_with_failover(
        [LLMAttempt("primary", primary)],
        retries_per_provider=1,
        retry_backoff_seconds=0,
    )

    assert result == "ok"
    assert primary.calls == 2


@pytest.mark.anyio
async def test_fails_over_to_next_provider_after_retry_exhausted() -> None:
    primary = ScriptedCall([ModelProviderError("down-1"), ModelProviderError("down-2")])
    fallback = ScriptedCall([])

    result = await run_llm_with_failover(
        [
            LLMAttempt("primary", primary),
            LLMAttempt("fallback", fallback),
        ],
        retries_per_provider=1,
        retry_backoff_seconds=0,
    )

    assert result == "ok"
    assert primary.calls == 2
    assert fallback.calls == 1


@pytest.mark.anyio
async def test_non_retryable_error_skips_retry_but_still_fails_over() -> None:
    primary = ScriptedCall([RuntimeError("unexpected crash")])
    fallback = ScriptedCall([])

    result = await run_llm_with_failover(
        [
            LLMAttempt("primary", primary),
            LLMAttempt("fallback", fallback),
        ],
        retries_per_provider=2,
        retry_backoff_seconds=0,
    )

    assert result == "ok"
    assert primary.calls == 1
    assert fallback.calls == 1


@pytest.mark.anyio
async def test_configuration_error_propagates_immediately() -> None:
    primary = ScriptedCall([ConfigurationError("bad config")])
    fallback = ScriptedCall([])

    with pytest.raises(ConfigurationError):
        await run_llm_with_failover(
            [
                LLMAttempt("primary", primary),
                LLMAttempt("fallback", fallback),
            ],
            retries_per_provider=1,
            retry_backoff_seconds=0,
        )

    assert primary.calls == 1
    assert fallback.calls == 0


@pytest.mark.anyio
async def test_reraises_last_echowhale_error_when_all_attempts_fail() -> None:
    primary = ScriptedCall([ModelProviderError("provider exploded")])

    with pytest.raises(ModelProviderError, match="provider exploded"):
        await run_llm_with_failover(
            [LLMAttempt("primary", primary)],
            retries_per_provider=0,
            retry_backoff_seconds=0,
        )


@pytest.mark.anyio
async def test_wraps_non_echowhale_error_when_all_attempts_fail() -> None:
    primary = ScriptedCall([RuntimeError("boom")])

    with pytest.raises(ModelProviderError, match="boom"):
        await run_llm_with_failover(
            [LLMAttempt("primary", primary)],
            retries_per_provider=0,
            retry_backoff_seconds=0,
        )


@pytest.mark.anyio
async def test_compose_failure_controls_final_error() -> None:
    def compose(failures: list[tuple[str, Exception]]) -> Exception:
        return UnsupportedSceneImageError("all unusable")

    primary = ScriptedCall([RuntimeError("boom")])

    with pytest.raises(UnsupportedSceneImageError, match="all unusable"):
        await run_llm_with_failover(
            [LLMAttempt("primary", primary)],
            retries_per_provider=0,
            retry_backoff_seconds=0,
            compose_failure=compose,
        )


@pytest.mark.anyio
async def test_deadline_skips_remaining_attempts(monkeypatch) -> None:
    clock = {"now": 0.0}

    def fake_monotonic() -> float:
        return clock["now"]

    monkeypatch.setattr(
        "api.integrations.llm.resilience.time",
        SimpleNamespace(monotonic=fake_monotonic),
    )

    async def slow_primary() -> str:
        clock["now"] += 50.0  # 调用本身耗尽全部预算
        raise ModelProviderError("timeout")

    fallback = ScriptedCall([])

    with pytest.raises(ModelProviderError):
        await run_llm_with_failover(
            [
                LLMAttempt("primary", slow_primary),
                LLMAttempt("fallback", fallback),
            ],
            retries_per_provider=0,
            retry_backoff_seconds=0,
            deadline_seconds=45,
        )

    assert fallback.calls == 0


@pytest.mark.anyio
async def test_empty_attempts_raise_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        await run_llm_with_failover([], retries_per_provider=1)


def test_is_retryable_llm_error_classification() -> None:
    assert is_retryable_llm_error(ModelProviderError("x"))
    assert is_retryable_llm_error(httpx.TimeoutException("t"))
    assert is_retryable_llm_error(httpx.ConnectError("c"))
    assert is_retryable_llm_error(ValueError("bad json"))
    assert not is_retryable_llm_error(ConfigurationError("bad config"))
    assert not is_retryable_llm_error(UnsupportedSceneImageError("gate"))
    assert not is_retryable_llm_error(RuntimeError("unexpected"))


@pytest.mark.anyio
async def test_attempt_failure_is_logged(caplog) -> None:
    primary = ScriptedCall([ModelProviderError("down")], result="ok")

    with caplog.at_level("WARNING", logger="api.integrations.llm.resilience"):
        await run_llm_with_failover(
            [LLMAttempt("primary", primary)],
            retries_per_provider=1,
            retry_backoff_seconds=0,
        )

    assert any("llm_attempt_failed" in record.message for record in caplog.records)
    assert any("primary" in record.message for record in caplog.records)
