"""OpenTelemetry 三层链路追踪基建（server / engine / provider attempt）。

与 request_context.py 同层的跨切面公共基建，语义见任务 design 2.1–2.2 节与
docs/observability.md。核心纪律：

- **模块级 tracer，不动全局 provider**：绝不调用 `trace.set_tracer_provider()`。
  全局 provider 只服务自动插桩库（本仓不用），手动埋点全部经自有 `_tracer` 引用，
  避开 OTel "provider 只能设一次"的全局约束，测试可整体替换 `_tracer` 零污染隔离。
- **关闭态零行为**（`settings.otel_enabled=False`，默认）：不 import SDK，tracer 走
  opentelemetry-api 的 no-op 路径（NonRecordingSpan，set_attribute / record_exception
  / set_status / update_name 均为安全空操作），零行为、近零开销。
- **旁路纪律**：任何追踪装配失败只降级 warning 并保持 no-op tracer，绝不影响业务；
  导出失败由 `_ResilientSpanExporter` 吞掉并限频 warning。埋点层不吞 BaseException
  来改变控制流——异常只被记账，随后原样上抛。
- **不落敏感内容**：span 只记关联 id / 模型名 / token 计数 / 终态与异常类型，
  不记 prompt、消息正文或任何密钥（logging-guidelines 同款红线）。
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Awaitable
from typing import Any, TypeVar

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

from api.common.request_context import get_request_id, get_request_owner
from api.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

# —— 属性键名统一（design 2.x 节），全仓 span 只用这一组键 ——
ATTR_REQUEST_ID = "echowhale.request_id"
ATTR_OWNER_ID = "echowhale.owner_id"
ATTR_SESSION_ID = "echowhale.session_id"
ATTR_TERMINAL = "echowhale.terminal"
ATTR_HTTP_METHOD = "http.method"
ATTR_HTTP_TARGET = "http.target"
ATTR_HTTP_ROUTE = "http.route"
ATTR_HTTP_STATUS_CODE = "http.status_code"
ATTR_ATTEMPT_NAME = "llm.attempt.name"
ATTR_RETRY_INDEX = "llm.retry_index"
ATTR_MODEL = "llm.model"
ATTR_USAGE_PROMPT_TOKENS = "llm.usage.prompt_tokens"
ATTR_USAGE_COMPLETION_TOKENS = "llm.usage.completion_tokens"
ATTR_USAGE_TOTAL_TOKENS = "llm.usage.total_tokens"

# 终态三值：与既有 failure policy 的 degraded 语义严格一致（design 2.3 映射表）。
TERMINAL_OK = "ok"
TERMINAL_DEGRADED = "degraded"
TERMINAL_FAILED = "failed"

_TRACER_NAME = "echowhale"
_DEFAULT_SERVICE_NAME = "echowhale-api"

# 模块级 tracer：configure_telemetry 开启态替换为 SDK tracer；测试可整体 monkeypatch。
# 惰性初始化为 opentelemetry-api 的 no-op tracer（关闭态永不触碰 SDK）。
_tracer: trace.Tracer | None = None
_configured = False

# traced_engine 的降级哨兵：degraded_result 未传时成功一律记 ok。
_UNSET = object()


def tracer() -> trace.Tracer:
    """返回模块级 tracer；关闭态是 opentelemetry-api 的 no-op tracer。"""
    global _tracer
    if _tracer is None:
        _tracer = trace.get_tracer(_TRACER_NAME)
    return _tracer


def configure_telemetry(*, span_exporter: Any | None = None) -> None:
    """启动期装配 tracer（main.py 启动区调用，幂等）。

    - 关闭态（默认）：直接返回，**不 import SDK**，tracer 保持 no-op——零行为。
    - 开启态：延迟 import SDK，构建 TracerProvider（Resource 吃标准
      OTEL_SERVICE_NAME / OTEL_RESOURCE_ATTRIBUTES 环境变量，仅在未设置时补默认
      `service.name=echowhale-api`）+ BatchSpanProcessor 包裹弹性导出器；
      `span_exporter` 参数仅供测试注入 InMemorySpanExporter。
    - 装配任何异常 → warning + 保持 no-op tracer（旁路纪律，业务照常启动）。
    """
    global _tracer, _configured
    if _configured:
        return
    _configured = True
    if not settings.otel_enabled:
        return
    try:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        delegate = span_exporter
        if delegate is None:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            delegate = OTLPSpanExporter()
        provider = TracerProvider(resource=_build_resource(Resource))
        provider.add_span_processor(BatchSpanProcessor(_ResilientSpanExporter(delegate)))
        _tracer = provider.get_tracer(_TRACER_NAME)
        logger.info("otel_telemetry_configured enabled=true")
    except Exception as exc:  # noqa: BLE001 - 观测装配失败必须与启动链路隔离
        logger.warning(
            "otel_configuration_failed degraded=true error=%s: %s", type(exc).__name__, exc
        )


def _build_resource(resource_cls: Any) -> Any:
    """构建 SDK Resource：标准环境变量优先，仅未设置 service.name 时补默认值。

    `Resource.create({})` 会合并 OTEL_SERVICE_NAME / OTEL_RESOURCE_ATTRIBUTES 与
    SDK 默认资源；用户未设置时 service.name 落在 `unknown_service:<进程>` 占位值上，
    以该占位为"未设置"信号补 `echowhale-api`，不覆盖用户的显式配置。
    """
    resource = resource_cls.create({})
    if str(resource.attributes.get("service.name", "")).startswith("unknown_service"):
        resource = resource.merge(resource_cls.create({"service.name": _DEFAULT_SERVICE_NAME}))
    return resource


class _ResilientSpanExporter:
    """导出器包装：export 失败吞掉并限频 warning，绝不影响业务链路。

    BatchSpanProcessor 本身也吞导出异常，但走 OTel 内部 logger 每批一条不可控；
    自家 logger 限频（单调钟 60 秒窗口一条）保证日志风暴可控、口径统一。
    导出器既可能抛异常（网络库直接 raise），也可能返回 FAILURE（OTLP 导出器把
    HTTP 错误吞成返回值）——两条路径同款处理，均记限频 warning。
    """

    WARNING_WINDOW_SECONDS = 60.0

    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate
        self._last_warning_at: float | None = None
        self._suppressed = 0

    def export(self, spans: Any) -> Any:
        from opentelemetry.sdk.trace.export import SpanExportResult

        try:
            result = self._delegate.export(spans)
        except Exception as exc:  # noqa: BLE001 - 导出失败必须与业务链路隔离
            self._warn_rate_limited(type(exc).__name__, str(exc))
            return SpanExportResult.FAILURE
        if result is not SpanExportResult.SUCCESS:
            self._warn_rate_limited("export_failure", str(result))
        return result

    def _warn_rate_limited(self, error_type: str, detail: str) -> None:
        """60 秒单调钟窗口内只打一条 warning，并汇总期间被抑制的失败次数。"""
        now = time.monotonic()
        self._suppressed += 1
        if (
            self._last_warning_at is not None
            and now - self._last_warning_at < self.WARNING_WINDOW_SECONDS
        ):
            return
        logger.warning(
            "otel_export_failed suppressed=%d error=%s: %s",
            self._suppressed - 1,
            error_type,
            detail,
        )
        self._last_warning_at = now
        self._suppressed = 0

    def shutdown(self) -> None:
        # 关停失败无补偿动作，不向进程边界传播（S110/SIM105：有意静默）。
        with contextlib.suppress(Exception):
            self._delegate.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> Any:
        from opentelemetry.sdk.trace.export import SpanExportResult

        try:
            return self._delegate.force_flush(timeout_millis)
        except Exception:  # noqa: BLE001 - 同 export：失败收敛为 FAILURE 返回值
            return SpanExportResult.FAILURE


def stamp_request_context(span: Span, *, session_id: str | None = None) -> None:
    """把 request-id / owner-id（与可选 session id）写上 span，跨层关联凭这些 id。

    owner 归因由 get_attribution_owner 在依赖解析处写入请求上下文，此处可得
    即写——traced_engine 与 resilience 的 attempt span 都经本函数，自动带上。
    """
    request_id = get_request_id()
    if request_id:
        span.set_attribute(ATTR_REQUEST_ID, request_id)
    owner_id = get_request_owner()
    if owner_id:
        span.set_attribute(ATTR_OWNER_ID, owner_id)
    if session_id:
        span.set_attribute(ATTR_SESSION_ID, session_id)


def stamp_llm_model(model: str) -> None:
    """把模型名写上**当时活跃** span（非 recording 直接返回，design 2.4）。

    整包路径活跃 span = llm.attempt；流式路径 usage 在流末帧才到达，
    attempt span 已随"开流"结束，属性落在当时活跃的 engine/server span 上
    （已知取舍，docs/observability.md 注明）。
    """
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute(ATTR_MODEL, model)


def stamp_llm_usage(
    model: str,
    *,
    prompt_tokens: Any,
    completion_tokens: Any,
    total_tokens: Any,
) -> None:
    """把模型名与 token 三元组写上当时活跃 span；字段缺失按 None 跳过。"""
    span = trace.get_current_span()
    if not span.is_recording():
        return
    span.set_attribute(ATTR_MODEL, model)
    if prompt_tokens is not None:
        span.set_attribute(ATTR_USAGE_PROMPT_TOKENS, prompt_tokens)
    if completion_tokens is not None:
        span.set_attribute(ATTR_USAGE_COMPLETION_TOKENS, completion_tokens)
    if total_tokens is not None:
        span.set_attribute(ATTR_USAGE_TOTAL_TOKENS, total_tokens)


def mark_failed(span: Span, exc: BaseException) -> None:
    """把 span 记为 failed：record_exception + Status ERROR + terminal=failed。

    只记账不改变控制流——调用方随后原样上抛，吞异常/降级转换仍属编排层职责。
    """
    span.record_exception(exc)
    span.set_attribute(ATTR_TERMINAL, TERMINAL_FAILED)
    span.set_status(Status(StatusCode.ERROR, f"{type(exc).__name__}: {exc}"))


async def traced_engine(
    name: str,
    awaitable: Awaitable[T],
    *,
    session_id: str | None = None,
    on_exception: str = TERMINAL_FAILED,
    degraded_result: Any = _UNSET,
) -> T:
    """engine 层异步包裹器（design 2.3）：建 `engine.{name}` current span 记账。

    - 进入时建 span 并写 request-id / session-id；
    - 成功按 `degraded_result` 哨兵判 ok/degraded（未传哨兵一律 ok）；
    - 异常（含 BaseException）按 `on_exception` 判终态并 record_exception 后
      **原样上抛**——吞异常/降级转换仍是编排层既有代码的职责，span 只如实记账；
    - terminal=failed 时置 Status ERROR；degraded 保持 OK 状态（本轮照常成功，
      失败痕迹由 record_exception 事件 + terminal 属性承载，见 observability.md）。
    """
    span_name = f"engine.{name}"
    with tracer().start_as_current_span(
        span_name,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        stamp_request_context(span, session_id=session_id)
        try:
            result = await awaitable
        except BaseException as exc:
            span.record_exception(exc)
            span.set_attribute(ATTR_TERMINAL, on_exception)
            if on_exception == TERMINAL_FAILED:
                span.set_status(Status(StatusCode.ERROR, f"{type(exc).__name__}: {exc}"))
            raise
        if degraded_result is not _UNSET and result is degraded_result:
            span.set_attribute(ATTR_TERMINAL, TERMINAL_DEGRADED)
        else:
            span.set_attribute(ATTR_TERMINAL, TERMINAL_OK)
        return result
