"""TracingMiddleware 单元/集成测试：server span 属性、路由模板、探针旁路、异常与关闭态。

用最小 FastAPI app 复刻 main.py 的中间件装配（Tracing 最先 add = 最内层，
RequestContext 在其外层），全程零真实网络；开启态经 conftest 的 recording_tracer
fixture 注入内存导出器，关闭态保持默认 no-op tracer。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.trace import StatusCode

from api.common.middleware import RequestContextMiddleware, TracingMiddleware


def _build_app() -> FastAPI:
    """与 main.py 同序的最小装配：Tracing 先 add（最内层），RequestContext 包外。"""
    app = FastAPI()
    app.add_middleware(TracingMiddleware)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        return {"status": "ready"}

    @app.post("/sessions/{session_id}/reply")
    def reply(session_id: str) -> dict[str, str]:
        return {"session_id": session_id}

    @app.get("/echo-context")
    async def echo_context() -> dict[str, bool]:
        # 直接探测请求处理期间 current span 是否在记录（关闭态锁定用）。
        return {"recording": trace.get_current_span().is_recording()}

    @app.get("/boom")
    async def boom() -> dict[str, str]:
        raise RuntimeError("downstream exploded")

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app())


# ---------- 开启态：server span 与属性 ----------


def test_server_span_records_request_id_method_status_and_route_template(
    recording_tracer, client: TestClient
) -> None:
    response = client.post("/sessions/sess_1/reply")

    assert response.status_code == 200
    request_id = response.headers["x-request-id"]

    (span,) = recording_tracer.get_finished_spans()
    # 响应头阶段用路由模板回填 span 名（低基数），不再是裸 HTTP POST。
    assert span.name == "HTTP POST /sessions/{session_id}/reply"
    attributes = span.attributes
    assert attributes["echowhale.request_id"] == request_id
    assert attributes["http.method"] == "POST"
    assert attributes["http.target"] == "/sessions/sess_1/reply"
    assert attributes["http.route"] == "/sessions/{session_id}/reply"
    assert attributes["http.status_code"] == 200
    assert attributes["echowhale.terminal"] == "ok"
    assert span.status.status_code is not StatusCode.ERROR


def test_server_span_without_route_keeps_method_level_name(recording_tracer) -> None:
    """路由模板不可得（404 未匹配）时保持 `HTTP {METHOD}` 名，回退 http.target。"""
    client = TestClient(_build_app())

    response = client.post("/no-such-route")

    assert response.status_code == 404
    (span,) = recording_tracer.get_finished_spans()
    assert span.name == "HTTP POST"
    assert span.attributes["http.target"] == "/no-such-route"
    assert "http.route" not in span.attributes


def test_health_and_readyz_probes_bypass_tracing(recording_tracer, client: TestClient) -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/readyz").status_code == 200

    assert list(recording_tracer.get_finished_spans()) == []


def test_downstream_exception_marks_failed_and_propagates(recording_tracer) -> None:
    """下游异常：record_exception + Status ERROR + terminal=failed 后原样上抛。"""
    client = TestClient(_build_app())  # raise_server_exceptions 默认 True

    with pytest.raises(RuntimeError, match="downstream exploded"):
        client.get("/boom")

    (span,) = recording_tracer.get_finished_spans()
    assert span.attributes["echowhale.terminal"] == "failed"
    assert span.status.status_code is StatusCode.ERROR
    assert any(
        (event.attributes.get("exception.type") or "").endswith("RuntimeError")
        for event in span.events
        if event.name == "exception"
    )
    # 异常路径未发响应：没有 status_code 属性，span 名保持方法级。
    assert span.name == "HTTP GET"
    assert "http.status_code" not in span.attributes


# ---------- 关闭态：零行为锁定 ----------


def test_closed_state_produces_no_recording_span_and_keeps_request_id(client: TestClient) -> None:
    """默认配置（otel_enabled=False）：请求期间 current span 不记录，链路照常。"""
    response = client.get("/echo-context")

    assert response.status_code == 200
    assert response.json() == {"recording": False}
    # request-id 中间件行为不受影响。
    assert response.headers["x-request-id"]


def test_closed_state_http_and_lifespan_scopes_pass_through() -> None:
    """关闭态纯 ASGI 行为：探针路径与非 http scope 直通，零 span 逻辑介入。"""

    async def downstream(scope: dict[str, Any], receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def noop_receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def noop_send(message: dict[str, Any]) -> None:
        return None

    async def exercise() -> list[int]:
        statuses: list[int] = []
        middleware = TracingMiddleware(downstream)
        for scope in (
            {"type": "http", "method": "GET", "path": "/health", "headers": []},
            {"type": "http", "method": "GET", "path": "/readyz", "headers": []},
            {"type": "lifespan"},
        ):
            sent: list[dict[str, Any]] = []

            async def send(message: dict[str, Any], *, sink: list[dict[str, Any]] = sent) -> None:
                sink.append(message)

            await middleware(scope, noop_receive, send)
            statuses.append(sent[0].get("status", 0))
        return statuses

    assert asyncio.run(exercise()) == [200, 200, 200]
