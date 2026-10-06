"""provider attempt 层 span 测试：failover/retry 的 span 序列与属性、live 客户端
usage 富集、流式路径 span 终止于开流（全程 httpx MockTransport，零真实网络）。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from api.common import telemetry
from api.common.exceptions import ConfigurationError, ModelProviderError
from api.common.request_context import reset_request_id, set_request_id
from api.common.telemetry import (
    ATTR_ATTEMPT_NAME,
    ATTR_MODEL,
    ATTR_REQUEST_ID,
    ATTR_RETRY_INDEX,
    ATTR_TERMINAL,
    ATTR_USAGE_COMPLETION_TOKENS,
    ATTR_USAGE_PROMPT_TOKENS,
    ATTR_USAGE_TOTAL_TOKENS,
    TERMINAL_FAILED,
    TERMINAL_OK,
)
from api.integrations.llm.openai import OpenAICompatibleClient
from api.integrations.llm.resilience import LLMAttempt, run_llm_with_failover


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


def _spans_by_name(exporter: Any, name: str) -> list[Any]:
    return [span for span in exporter.get_finished_spans() if span.name == name]


# ---------- failover / retry 的 attempt span 序列 ----------


@pytest.mark.anyio
async def test_success_attempt_span_carries_attributes(span_exporter, recording_tracer) -> None:
    token = set_request_id("req_attempt_ok")
    try:
        primary = ScriptedCall([])
        result = await run_llm_with_failover(
            [LLMAttempt("text_primary", primary)],
            retries_per_provider=1,
            retry_backoff_seconds=0,
        )
    finally:
        reset_request_id(token)

    assert result == "ok"
    (span,) = _spans_by_name(span_exporter, "llm.attempt")
    assert span.attributes[ATTR_ATTEMPT_NAME] == "text_primary"
    assert span.attributes[ATTR_RETRY_INDEX] == 0
    assert span.attributes[ATTR_REQUEST_ID] == "req_attempt_ok"
    assert span.attributes[ATTR_TERMINAL] == TERMINAL_OK


@pytest.mark.anyio
async def test_retry_produces_failed_then_ok_attempt_spans(span_exporter, recording_tracer) -> None:
    """同 provider 重试：失败 attempt 与成功 attempt 各一个 span（failover 即序列）。"""
    token = set_request_id("req_retry")
    try:
        primary = ScriptedCall([ModelProviderError("transient")])
        result = await run_llm_with_failover(
            [LLMAttempt("text_primary", primary)],
            retries_per_provider=1,
            retry_backoff_seconds=0,
        )
    finally:
        reset_request_id(token)

    assert result == "ok"
    spans = _spans_by_name(span_exporter, "llm.attempt")
    assert [span.attributes[ATTR_RETRY_INDEX] for span in spans] == [0, 1]
    failed_span, ok_span = spans
    assert failed_span.attributes[ATTR_TERMINAL] == TERMINAL_FAILED
    assert failed_span.status.status_code.name == "ERROR"
    assert any(
        (event.attributes.get("exception.type") or "").endswith("ModelProviderError")
        for event in failed_span.events
        if event.name == "exception"
    )
    assert ok_span.attributes[ATTR_TERMINAL] == TERMINAL_OK
    assert ok_span.status.status_code.name != "ERROR"


@pytest.mark.anyio
async def test_failover_sequence_records_every_failed_attempt(
    span_exporter, recording_tracer
) -> None:
    """全败：primary 两次重试 + fallback 两次重试，每个失败 attempt 独立记账。"""
    token = set_request_id("req_failover")
    try:
        primary = ScriptedCall([ModelProviderError("down-1"), ModelProviderError("down-2")])
        fallback = ScriptedCall([ModelProviderError("down-3"), ModelProviderError("down-4")])
        with pytest.raises(ModelProviderError, match="down-4"):
            await run_llm_with_failover(
                [
                    LLMAttempt("text_primary", primary),
                    LLMAttempt("text_fallback", fallback),
                ],
                retries_per_provider=1,
                retry_backoff_seconds=0,
            )
    finally:
        reset_request_id(token)

    spans = _spans_by_name(span_exporter, "llm.attempt")
    assert [
        (span.attributes[ATTR_ATTEMPT_NAME], span.attributes[ATTR_RETRY_INDEX]) for span in spans
    ] == [
        ("text_primary", 0),
        ("text_primary", 1),
        ("text_fallback", 0),
        ("text_fallback", 1),
    ]
    assert all(span.attributes[ATTR_TERMINAL] == TERMINAL_FAILED for span in spans)


@pytest.mark.anyio
async def test_non_retryable_error_yields_single_failed_attempt(
    span_exporter, recording_tracer
) -> None:
    primary = ScriptedCall([RuntimeError("unexpected crash")])
    fallback = ScriptedCall([])

    result = await run_llm_with_failover(
        [LLMAttempt("text_primary", primary), LLMAttempt("text_fallback", fallback)],
        retries_per_provider=2,
        retry_backoff_seconds=0,
    )

    assert result == "ok"
    assert len(_spans_by_name(span_exporter, "llm.attempt")) == 2  # 每个 provider 各一次


@pytest.mark.anyio
async def test_configuration_error_marks_span_failed_before_reraise(
    span_exporter, recording_tracer
) -> None:
    """ConfigurationError 立即上抛，但 attempt span 先记 failed。"""
    primary = ScriptedCall([ConfigurationError("bad config")])

    with pytest.raises(ConfigurationError):
        await run_llm_with_failover([LLMAttempt("text_primary", primary)], retries_per_provider=1)

    (span,) = _spans_by_name(span_exporter, "llm.attempt")
    assert span.attributes[ATTR_TERMINAL] == TERMINAL_FAILED
    assert any(
        (event.attributes.get("exception.type") or "").endswith("ConfigurationError")
        for event in span.events
        if event.name == "exception"
    )


@pytest.mark.anyio
async def test_cancelled_attempt_marks_failed_and_reraises(span_exporter, recording_tracer) -> None:
    class CancelledCall:
        async def __call__(self) -> str:
            raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await run_llm_with_failover([LLMAttempt("text_primary", CancelledCall())])

    (span,) = _spans_by_name(span_exporter, "llm.attempt")
    assert span.attributes[ATTR_TERMINAL] == TERMINAL_FAILED
    assert any(
        (event.attributes.get("exception.type") or "").endswith("CancelledError")
        for event in span.events
        if event.name == "exception"
    )


@pytest.mark.anyio
async def test_attempt_spans_are_children_of_current_engine_span(
    span_exporter, recording_tracer
) -> None:
    primary = ScriptedCall([])
    with telemetry.tracer().start_as_current_span("engine.coach") as engine_span:
        await run_llm_with_failover([LLMAttempt("text_primary", primary)])

    (attempt,) = _spans_by_name(span_exporter, "llm.attempt")
    outer = next(span for span in span_exporter.get_finished_spans() if span.name == "engine.coach")
    assert attempt.parent.span_id == engine_span.get_span_context().span_id
    assert attempt.parent.span_id == outer.get_span_context().span_id


# ---------- live 客户端路径（httpx MockTransport，零真实网络） ----------


def _json_transport(usage: dict[str, Any] | None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body: dict[str, Any] = {"choices": [{"message": {"content": "Hello there!"}}]}
        if usage is not None:
            body["usage"] = usage
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


@pytest.mark.anyio
async def test_live_client_attempt_span_carries_model_and_token_triple(
    span_exporter, recording_tracer
) -> None:
    """整包路径：usage 流经 _record_usage 时 stamp 到当时活跃的 attempt span。"""
    client = OpenAICompatibleClient(
        base_url="https://llm.test",
        api_key="key",
        model="demo-model",
        timeout_seconds=5,
        transport=_json_transport(
            {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}
        ),
    )

    with telemetry.tracer().start_as_current_span("engine.feedback"):
        result = await run_llm_with_failover(
            [
                LLMAttempt(
                    "text_primary",
                    lambda: client.async_complete_text(system_prompt="sys", user_prompt="usr"),
                )
            ]
        )

    assert result == "Hello there!"
    (attempt,) = _spans_by_name(span_exporter, "llm.attempt")
    assert attempt.attributes[ATTR_MODEL] == "demo-model"
    assert attempt.attributes[ATTR_USAGE_PROMPT_TOKENS] == 12
    assert attempt.attributes[ATTR_USAGE_COMPLETION_TOKENS] == 3
    assert attempt.attributes[ATTR_USAGE_TOTAL_TOKENS] == 15


def _sse_transport(frames: list[dict[str, Any]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = "".join(f"data: {json.dumps(frame)}\n\n" for frame in frames)
        payload += "data: [DONE]\n\n"
        return httpx.Response(
            200, content=payload.encode("utf-8"), headers={"content-type": "text/event-stream"}
        )

    return httpx.MockTransport(handler)


@pytest.mark.anyio
async def test_stream_attempt_span_ends_on_open_and_usage_lands_on_engine_span(
    span_exporter,
    recording_tracer,
) -> None:
    """流式路径已知取舍：attempt span 只覆盖开流；流末帧 usage 落在当时活跃 span。"""
    client = OpenAICompatibleClient(
        base_url="https://llm.test",
        api_key="key",
        model="demo-model",
        timeout_seconds=5,
        transport=_sse_transport(
            [
                {"choices": [{"delta": {"content": "Hello"}}]},
                {
                    "choices": [],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
                },
            ]
        ),
        stream_include_usage=True,
    )

    with telemetry.tracer().start_as_current_span("engine.coach"):
        # 开流阶段：attempt span 在 failover 返回流对象时即结束。
        stream = await run_llm_with_failover(
            [
                LLMAttempt(
                    "text_primary",
                    lambda: client.async_open_text_stream(system_prompt="sys", user_prompt="usr"),
                )
            ]
        )
        (attempt,) = _spans_by_name(span_exporter, "llm.attempt")
        assert attempt.attributes[ATTR_TERMINAL] == TERMINAL_OK
        assert ATTR_MODEL in attempt.attributes  # 开流前 payload builder 已 stamp
        assert ATTR_USAGE_TOTAL_TOKENS not in attempt.attributes

        # 消费阶段：流末帧 usage 到达时 attempt span 已结束，落在 engine span 上。
        deltas = [delta async for delta in stream.aiter_deltas()]
        await stream.aclose()

    assert deltas == ["Hello"]
    (engine,) = [span for span in span_exporter.get_finished_spans() if span.name == "engine.coach"]
    assert engine.attributes[ATTR_MODEL] == "demo-model"
    assert engine.attributes[ATTR_USAGE_PROMPT_TOKENS] == 5
    assert engine.attributes[ATTR_USAGE_COMPLETION_TOKENS] == 2
    assert engine.attributes[ATTR_USAGE_TOTAL_TOKENS] == 7
