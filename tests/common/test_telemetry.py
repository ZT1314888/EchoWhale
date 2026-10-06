"""telemetry 基建单元测试：关闭态锁定、终态映射、stamp 助手、弹性导出器、装配。

隔离铁律：全程不碰 trace.set_tracer_provider()；recording 场景经 conftest 的
recording_tracer fixture（独立 SDK TracerProvider + monkeypatch 换 _tracer）。
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.trace import StatusCode

from api.common import telemetry
from api.common.exceptions import ModelProviderError
from api.common.request_context import reset_request_id, set_request_id
from api.common.telemetry import (
    ATTR_MODEL,
    ATTR_REQUEST_ID,
    ATTR_SESSION_ID,
    ATTR_TERMINAL,
    ATTR_USAGE_COMPLETION_TOKENS,
    ATTR_USAGE_PROMPT_TOKENS,
    ATTR_USAGE_TOTAL_TOKENS,
    TERMINAL_DEGRADED,
    TERMINAL_FAILED,
    TERMINAL_OK,
    _ResilientSpanExporter,
    configure_telemetry,
    mark_failed,
    stamp_llm_model,
    stamp_llm_usage,
    traced_engine,
)

# ---------- 关闭态 no-op 锁定 ----------


def test_default_tracer_produces_non_recording_spans() -> None:
    """默认（otel_enabled=False）：tracer 产出的 span 不记录，属性/状态安全空操作。"""
    tracer = telemetry.tracer()

    with tracer.start_as_current_span("noop") as span:
        assert span.is_recording() is False
        # no-op span 的写操作必须全部安全（零行为承诺）。
        span.set_attribute("k", "v")
        span.record_exception(RuntimeError("ignored"))
        span.set_status(StatusCode.ERROR)
        span.update_name("renamed")


def test_configure_telemetry_disabled_keeps_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """关闭态 configure 直接返回：不 import SDK、不替换 no-op tracer。"""
    monkeypatch.setattr(telemetry, "_configured", False)
    monkeypatch.setattr(telemetry, "_tracer", None)
    monkeypatch.setattr(telemetry.settings, "otel_enabled", False)

    configure_telemetry()

    assert telemetry._tracer is None
    with telemetry.tracer().start_as_current_span("noop") as span:
        assert span.is_recording() is False


# ---------- configure_telemetry 开启态装配 ----------


def test_configure_telemetry_enabled_wires_inmemory_exporter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """开启态：注入 InMemorySpanExporter 后 tracer 产出可记录 span 并落导出器。"""
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor as _RealBatchSpanProcessor,
    )
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    monkeypatch.setattr(telemetry, "_configured", False)
    monkeypatch.setattr(telemetry, "_tracer", None)
    monkeypatch.setattr(telemetry.settings, "otel_enabled", True)

    # 用 SimpleSpanProcessor 替换 BatchSpanProcessor：同步导出让断言确定性成立
    # （真实 BSP 的 5s 批处理延迟会让内存导出器断言变成竞态；BSP 本身是 OTel
    # 薄壳，弹性导出器已单独覆盖）。
    monkeypatch.setattr(
        "opentelemetry.sdk.trace.export.BatchSpanProcessor",
        SimpleSpanProcessor,
        raising=True,
    )
    assert _RealBatchSpanProcessor is not None  # 保留真实类引用，防误改 import

    configure_telemetry(span_exporter=exporter)
    try:
        with telemetry.tracer().start_as_current_span("wired") as span:
            assert span.is_recording() is True
        assert len(exporter.get_finished_spans()) == 1

        # 幂等：第二次调用不得替换已装配的 tracer。
        first_tracer = telemetry._tracer
        configure_telemetry(span_exporter=InMemorySpanExporter())
        assert telemetry._tracer is first_tracer
    finally:
        # 复位模块状态，避免 SDK tracer（BatchSpanProcessor 后台线程）泄漏到后续用例。
        monkeypatch.setattr(telemetry, "_tracer", None)
        monkeypatch.setattr(telemetry, "_configured", False)


def test_configure_telemetry_assembly_failure_degrades_to_noop(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """装配异常只降级 warning，tracer 保持 no-op，启动链路不受影响。"""
    monkeypatch.setattr(telemetry, "_configured", False)
    monkeypatch.setattr(telemetry, "_tracer", None)
    monkeypatch.setattr(telemetry.settings, "otel_enabled", True)

    def boom(_resource_cls: object) -> object:
        raise RuntimeError("resource assembly exploded")

    monkeypatch.setattr(telemetry, "_build_resource", boom)

    with caplog.at_level(logging.WARNING, logger="api.common.telemetry"):
        configure_telemetry()

    assert telemetry._tracer is None
    assert any("otel_configuration_failed" in record.message for record in caplog.records)
    with telemetry.tracer().start_as_current_span("noop") as span:
        assert span.is_recording() is False


# ---------- traced_engine 终态映射（design 2.3 表） ----------


def _request_id_ctx(request_id: str):
    token = set_request_id(request_id)
    return token


@pytest.mark.anyio
async def test_traced_engine_success_marks_ok(recording_tracer, span_exporter) -> None:
    token = _request_id_ctx("req_ok")
    try:

        async def work() -> str:
            return "done"

        result = await traced_engine("feedback", work(), session_id="sess_1")

        assert result == "done"
    finally:
        reset_request_id(token)

    (span,) = span_exporter.get_finished_spans()
    assert span.name == "engine.feedback"
    assert span.attributes[ATTR_TERMINAL] == TERMINAL_OK
    assert span.attributes[ATTR_REQUEST_ID] == "req_ok"
    assert span.attributes[ATTR_SESSION_ID] == "sess_1"


@pytest.mark.anyio
async def test_traced_engine_degraded_result_marks_degraded(
    recording_tracer, span_exporter
) -> None:
    """review 分支：copy=None（哨兵命中）记 degraded；非 None 记 ok。"""

    async def mock_short_circuit() -> None:
        return None

    await traced_engine("review", mock_short_circuit(), degraded_result=None)

    async def live_copy() -> str:
        return "copy"

    await traced_engine("review", live_copy(), degraded_result=None)

    degraded_span, ok_span = span_exporter.get_finished_spans()
    assert degraded_span.attributes[ATTR_TERMINAL] == TERMINAL_DEGRADED
    assert ok_span.attributes[ATTR_TERMINAL] == TERMINAL_OK


@pytest.mark.anyio
async def test_traced_engine_exception_failed_records_error_and_reraises(
    recording_tracer,
    span_exporter,
) -> None:
    """coach 分支：异常记 failed + Status ERROR + record_exception，原样上抛。"""

    async def explodes() -> str:
        raise ModelProviderError("coach down")

    with pytest.raises(ModelProviderError, match="coach down"):
        await traced_engine("coach", explodes())

    (span,) = span_exporter.get_finished_spans()
    assert span.attributes[ATTR_TERMINAL] == TERMINAL_FAILED
    assert span.status.status_code is StatusCode.ERROR
    events = span.events
    assert any(event.name == "exception" for event in events)
    assert any(
        (event.attributes.get("exception.type") or "").endswith("ModelProviderError")
        for event in events
    )


@pytest.mark.anyio
async def test_traced_engine_exception_degraded_keeps_ok_status(
    recording_tracer, span_exporter
) -> None:
    """feedback 分支：异常按 degraded 记账（本轮照常成功），状态不置 ERROR。"""

    async def explodes() -> str:
        raise RuntimeError("feedback provider down")

    with pytest.raises(RuntimeError, match="feedback provider down"):
        await traced_engine("feedback", explodes(), on_exception=TERMINAL_DEGRADED)

    (span,) = span_exporter.get_finished_spans()
    assert span.attributes[ATTR_TERMINAL] == TERMINAL_DEGRADED
    assert span.status.status_code is not StatusCode.ERROR
    assert any(event.name == "exception" for event in span.events)


@pytest.mark.anyio
async def test_traced_engine_base_exception_recorded_and_reraised(
    recording_tracer, span_exporter
) -> None:
    """取消（CancelledError 等 BaseException）不吞：记账后原样上抛。"""

    async def cancelled() -> str:
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await traced_engine("coach", cancelled())

    (span,) = span_exporter.get_finished_spans()
    assert span.attributes[ATTR_TERMINAL] == TERMINAL_FAILED
    assert any(
        (event.attributes.get("exception.type") or "").endswith("CancelledError")
        for event in span.events
        if event.name == "exception"
    )


@pytest.mark.anyio
async def test_traced_engine_span_is_current_inside_and_parent_of_child(
    recording_tracer, span_exporter
) -> None:
    """engine span 在 await 期间是 current span（llm.attempt 挂其下的前提）。"""

    async def work() -> None:
        current = telemetry.trace.get_current_span()
        assert current.is_recording() is True

    with telemetry.tracer().start_as_current_span("outer") as outer:
        await traced_engine("coach", work())

    engine_span, outer_span = span_exporter.get_finished_spans()
    assert engine_span.name == "engine.coach"
    assert engine_span.parent.span_id == outer.get_span_context().span_id
    assert outer_span.name == "outer"


# ---------- stamp 助手 ----------


def test_stamp_llm_model_and_usage_on_recording_span(recording_tracer, span_exporter) -> None:
    with telemetry.tracer().start_as_current_span("attempt") as span:
        stamp_llm_model("qwen-max")
        stamp_llm_usage(
            "qwen-max",
            prompt_tokens=12,
            completion_tokens=3,
            total_tokens=15,
        )
        assert span.is_recording() is True

    (recorded,) = span_exporter.get_finished_spans()
    assert recorded.attributes[ATTR_MODEL] == "qwen-max"
    assert recorded.attributes[ATTR_USAGE_PROMPT_TOKENS] == 12
    assert recorded.attributes[ATTR_USAGE_COMPLETION_TOKENS] == 3
    assert recorded.attributes[ATTR_USAGE_TOTAL_TOKENS] == 15


def test_stamp_llm_usage_skips_missing_token_fields(recording_tracer, span_exporter) -> None:
    with telemetry.tracer().start_as_current_span("attempt"):
        stamp_llm_usage("qwen-max", prompt_tokens=None, completion_tokens=None, total_tokens=None)

    (recorded,) = span_exporter.get_finished_spans()
    assert recorded.attributes[ATTR_MODEL] == "qwen-max"
    assert ATTR_USAGE_PROMPT_TOKENS not in recorded.attributes
    assert ATTR_USAGE_TOTAL_TOKENS not in recorded.attributes


def test_stamp_llm_helpers_are_noop_without_recording_span() -> None:
    """无活跃 recording span（关闭态默认）：stamp 直接返回，零副作用。"""
    stamp_llm_model("qwen-max")
    stamp_llm_usage("qwen-max", prompt_tokens=1, completion_tokens=1, total_tokens=2)


def test_mark_failed_sets_terminal_status_and_exception(recording_tracer, span_exporter) -> None:
    with telemetry.tracer().start_as_current_span("server") as span:
        mark_failed(span, RuntimeError("downstream exploded"))

    (recorded,) = span_exporter.get_finished_spans()
    assert recorded.attributes[ATTR_TERMINAL] == TERMINAL_FAILED
    assert recorded.status.status_code is StatusCode.ERROR
    assert any(
        (event.attributes.get("exception.type") or "").endswith("RuntimeError")
        for event in recorded.events
        if event.name == "exception"
    )


# ---------- _ResilientSpanExporter：吞错 + 限频 warning ----------


class _ExplodingExporter:
    def __init__(self) -> None:
        self.calls = 0

    def export(self, spans: object) -> object:
        self.calls += 1
        raise RuntimeError("network down")


class _StaticExporter:
    def __init__(self, result: object) -> None:
        self._result = result

    def export(self, spans: object) -> object:
        return self._result


def _fake_clock(start: float):
    state = {"now": start}

    def monotonic() -> float:
        return state["now"]

    return state, monotonic


def test_resilient_exporter_swallows_exception_and_returns_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    delegate = _ExplodingExporter()
    exporter = _ResilientSpanExporter(delegate)

    with caplog.at_level(logging.WARNING, logger="api.common.telemetry"):
        result = exporter.export([])

    assert result is SpanExportResult.FAILURE
    assert delegate.calls == 1
    assert any("otel_export_failed" in record.message for record in caplog.records)


def test_resilient_exporter_rate_limits_warning_to_one_per_window(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    state, monotonic = _fake_clock(1000.0)
    monkeypatch.setattr(telemetry, "time", SimpleNamespace(monotonic=monotonic))
    exporter = _ResilientSpanExporter(_ExplodingExporter())

    with caplog.at_level(logging.WARNING, logger="api.common.telemetry"):
        exporter.export([])  # 第一次失败 → 打 1 条 warning
        exporter.export([])  # 60s 窗口内 → 抑制
        exporter.export([])  # 仍抑制
        state["now"] += 61.0
        exporter.export([])  # 窗口外 → 再打 1 条，汇总 suppressed=2

    warnings = [record for record in caplog.records if "otel_export_failed" in record.message]
    assert len(warnings) == 2
    assert "suppressed=2" in warnings[-1].getMessage()


def test_resilient_exporter_warns_on_failure_result_passthrough(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """OTLP 导出器把 HTTP 错误吞成 FAILURE 返回值：同样限频记账，结果透传。"""
    _state, monotonic = _fake_clock(0.0)
    monkeypatch.setattr(telemetry, "time", SimpleNamespace(monotonic=monotonic))
    exporter = _ResilientSpanExporter(_StaticExporter(SpanExportResult.FAILURE))

    with caplog.at_level(logging.WARNING, logger="api.common.telemetry"):
        assert exporter.export([]) is SpanExportResult.FAILURE
        assert exporter.export([]) is SpanExportResult.FAILURE

    warnings = [record for record in caplog.records if "otel_export_failed" in record.message]
    assert len(warnings) == 1


def test_resilient_exporter_success_passthrough_is_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    exporter = _ResilientSpanExporter(_StaticExporter(SpanExportResult.SUCCESS))

    with caplog.at_level(logging.WARNING, logger="api.common.telemetry"):
        assert exporter.export([]) is SpanExportResult.SUCCESS

    assert not [record for record in caplog.records if "otel_export_failed" in record.message]


def test_resilient_exporter_shutdown_and_force_flush_never_raise() -> None:
    class ShutdownBoom:
        def export(self, spans: object) -> object:
            return SpanExportResult.SUCCESS

        def shutdown(self) -> None:
            raise RuntimeError("shutdown boom")

        def force_flush(self, timeout_millis: int = 30000) -> object:
            raise RuntimeError("flush boom")

    exporter = _ResilientSpanExporter(ShutdownBoom())

    exporter.shutdown()
    assert exporter.force_flush() is SpanExportResult.FAILURE
