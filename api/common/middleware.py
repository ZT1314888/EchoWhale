from __future__ import annotations

import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from api.common.exceptions import FileTooLargeError
from api.common.request_context import (
    REQUEST_ID_HEADER,
    ensure_request_id,
    get_request_id,
    reset_request_id,
    set_request_id,
)
from api.common.responses import ApiResponse
from api.common.telemetry import (
    ATTR_HTTP_METHOD,
    ATTR_HTTP_ROUTE,
    ATTR_HTTP_STATUS_CODE,
    ATTR_HTTP_TARGET,
    ATTR_REQUEST_ID,
    ATTR_TERMINAL,
    TERMINAL_OK,
    mark_failed,
    tracer,
)
from api.core.config import settings

logger = logging.getLogger(__name__)

BODY_TOO_LARGE_MESSAGE = "Request body too large"

# 基础设施探针路径：每 5–30s 一跳的 liveness/readiness 请求不打 server span，
# 噪声大于价值（design 2.2）。仅开启态涉及；关闭态整条路径本来就无 span。
HEALTH_PROBE_PATHS = frozenset({"/health", "/readyz"})

# ASGI 三件套的类型别名：纯 ASGI 中间件只面向 receive/send 回调，
# 不持有 Request 对象，也就不依赖 BaseHTTPMiddleware 的全量缓冲行为。
Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


class _BodySizeExceeded(Exception):
    """内部哨兵异常：超限后终止下游对请求体的继续消费，不逃出本中间件。"""


class BodySizeLimitMiddleware:
    """全局请求体大小门（纯 ASGI 实现，语义见任务 design 第 2 节）。

    为什么不用 BaseHTTPMiddleware：它会先把整个请求体缓冲进内存才放行下游，
    本中间件要防的恰恰是超大 body 打爆进程内存，套它等于白防。

    - 头部声明 Content-Length 且超上限：不读 body、不进下游 app，直接回 413 统一信封；
    - 无 Content-Length（chunked）：转发过程中按块计数，超限先发 413 再停止转发——
      宁可让下游的 multipart 解析因截断失败，也不把超限 body 全部读完
      （任务 design 第 7 节权衡：客户端确定拿到 413 优先于日志干净）；
    - 仅处理 http scope，lifespan / websocket 直通。
    """

    def __init__(self, app: Any, *, max_body_bytes: int | None = None) -> None:
        self.app = app
        # 默认上限来自 settings（12MB = 10MB 媒体 + multipart 余量），
        # 测试可注入更小的 cap 以便低成本覆盖截断路径。
        self.max_body_bytes = (
            settings.max_request_body_bytes if max_body_bytes is None else max_body_bytes
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = self._declared_content_length(scope)
        if declared is not None:
            if declared > self.max_body_bytes:
                logger.info(
                    "request_body_rejected reason=declared_content_length " "declared=%d cap=%d",
                    declared,
                    self.max_body_bytes,
                )
                await self._send_rejection(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return

        await self._guard_streaming_body(scope, receive, send)

    async def _guard_streaming_body(self, scope: Scope, receive: Receive, send: Send) -> None:
        """无 Content-Length 的请求：包装 receive 逐块计数，超限即断。"""
        total = 0
        response_started = False

        async def tracking_send(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        async def counting_receive() -> dict[str, Any]:
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_body_bytes:
                    logger.info(
                        "request_body_rejected reason=streamed_body accumulated=%d cap=%d",
                        total,
                        self.max_body_bytes,
                    )
                    # 先发 413 再停止转发，保证客户端拿到确定响应；若下游已经在
                    # 发响应（流式场景），则跳过本次发送避免双响应协议冲突。
                    if not response_started:
                        await self._send_rejection(scope, receive, send)
                    raise _BodySizeExceeded
            return message

        # 超限后下游的收尾失败（如 multipart 解析中断）一并吞掉，请求到此为止，
        # 哨兵异常绝不逃出本中间件（否则会被外层当作服务器错误记 500）。
        with contextlib.suppress(_BodySizeExceeded):
            await self.app(scope, counting_receive, tracking_send)

    @staticmethod
    def _declared_content_length(scope: Scope) -> int | None:
        for name, value in scope.get("headers") or []:
            if name == b"content-length":
                try:
                    return int(value)
                except ValueError:
                    # 非法 Content-Length 不在此拦截，交给框架的请求解析报错。
                    return None
        return None

    @staticmethod
    async def _send_rejection(scope: Scope, receive: Receive, send: Send) -> None:
        # 413 复用 ApiResponse.failed 的序列化形态，与全局异常处理器的信封完全一致；
        # body_code 取 FileTooLargeError.code（1001），与媒体超限同一语义族。
        await ApiResponse.failed(
            message=BODY_TOO_LARGE_MESSAGE,
            body_code=FileTooLargeError.code,
            http_code=413,
        )(scope, receive, send)


class RequestContextMiddleware:
    """请求关联 ID 中间件（纯 ASGI 实现，语义见任务 design 第 2 节）。

    - 入站 X-Request-ID 合法（非空、≤64 可打印 ASCII 字符）则复用，否则生成
      `req_<16hex>` 新 id——不信任超长 / 含控制字符的入站值；
    - id 注入 ContextVar，应用内任意 logger 调用经 RequestIdFilter 自动携带，
      多轮链路（反馈 + 教练 + 流式 + 落库）的日志可凭同一 id 串起来；
    - 响应头回写 X-Request-ID：包装 send 只改 http.response.start——SSE 等
      流式响应的头在开流前发送，因此同样生效；
    - 仅处理 http scope，lifespan / websocket 直通。
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = ensure_request_id(scope)
        token = set_request_id(request_id)

        async def send_with_request_id(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                # 只在响应头消息上追加，body 消息原样透传；setdefault 兼容
                # 下游没放 headers 键的裸 ASGI 响应。
                message.setdefault("headers", []).append(
                    (REQUEST_ID_HEADER.encode("latin-1"), request_id.encode("latin-1"))
                )
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            # 正常返回与下游异常都要复位：请求结束后同线程的后台日志不得再挂旧 id。
            reset_request_id(token)


class TracingMiddleware:
    """server 层 span 中间件（纯 ASGI 实现，语义见任务 design 2.2 节）。

    挂在 request-id 中间件内层（main.py 第一个 add_middleware = 最内层），
    进入时 ContextVar 已建立，server span 可直接携带 request-id：

    - span 名创建时为 `HTTP {METHOD}`，响应头阶段读 `scope["route"]`（FastAPI
      路由器解析后会写回 scope）拿路由模板，`update_name` 成 `HTTP {METHOD}
      {template}` 并补 `http.route` 属性——模板低基数，避免含会话 id 的原始
      path 撑爆聚合维度；拿不到则保持方法级名（依赖 `http.target` 属性）；
    - 下游异常：record_exception + Status ERROR + terminal=failed 后**原样上抛**
      （不吞，全局异常处理器语义不变）；
    - `/health`、`/readyz` 探针直通不打 span；仅处理 http scope，
      lifespan / websocket 直通；
    - 关闭态 tracer 是 no-op：span 全程 NonRecordingSpan，零行为。
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in HEALTH_PROBE_PATHS:
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        attributes: dict[str, Any] = {
            ATTR_HTTP_METHOD: method,
            ATTR_HTTP_TARGET: scope.get("path", ""),
        }
        request_id = get_request_id()
        if request_id:
            attributes[ATTR_REQUEST_ID] = request_id

        with tracer().start_as_current_span(
            f"HTTP {method}",
            attributes=attributes,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:

            async def tracing_send(message: dict[str, Any]) -> None:
                if message["type"] == "http.response.start":
                    status_code = message.get("status")
                    if status_code is not None:
                        span.set_attribute(ATTR_HTTP_STATUS_CODE, status_code)
                    # 路由模板在响应头阶段才可得：路由器在 scope 上回写 route 对象。
                    template = getattr(scope.get("route"), "path", None)
                    if template:
                        span.update_name(f"HTTP {method} {template}")
                        span.set_attribute(ATTR_HTTP_ROUTE, template)
                await send(message)

            try:
                await self.app(scope, receive, tracing_send)
            except BaseException as exc:
                # 只记账不改控制流：异常原样上抛，交全局异常处理器。
                mark_failed(span, exc)
                raise
            span.set_attribute(ATTR_TERMINAL, TERMINAL_OK)
