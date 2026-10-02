from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from api.common.middleware import RequestContextMiddleware
from api.common.request_context import (
    MAX_INBOUND_REQUEST_ID_LENGTH,
    configure_request_id_logging,
    ensure_request_id,
    generate_request_id,
    get_request_id,
    is_reusable_request_id,
)

REQUEST_ID_PATTERN = re.compile(r"^req_[0-9a-f]{16}$")

TEST_LOGGER = logging.getLogger("api.tests.request_context")


class ContextProbeApp:
    """下游替身：记录中间件注入的 request id，并回一个最小 ASGI 响应。"""

    def __init__(self) -> None:
        self.seen_request_id: str | None = None

    async def __call__(self, scope: dict[str, Any], receive, send) -> None:
        self.seen_request_id = get_request_id()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


def http_scope(headers: list[tuple[bytes, bytes]]) -> dict[str, Any]:
    return {"type": "http", "method": "GET", "path": "/x", "headers": headers}


def call_middleware(
    downstream: ContextProbeApp, headers: list[tuple[bytes, bytes]]
) -> list[dict[str, Any]]:
    """跑一遍中间件，返回下游发出的全部 ASGI 消息（一次事件循环内完成）。"""

    async def scenario() -> list[dict[str, Any]]:
        sent: list[dict[str, Any]] = []

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        await RequestContextMiddleware(downstream)(http_scope(headers), receive, send)
        return sent

    return asyncio.run(scenario())


def response_start(sent: list[dict[str, Any]]) -> dict[str, Any]:
    return sent[0]


def start_header_values(sent: list[dict[str, Any]], name: bytes) -> list[bytes]:
    return [value for key, value in response_start(sent).get("headers", []) if key == name]


def test_inbound_id_is_reused_end_to_end() -> None:
    """合法入站 id：下游 ContextVar 可见，响应头原样回写同一 id。"""
    downstream = ContextProbeApp()

    sent = call_middleware(downstream, [(b"x-request-id", b"abc-123")])

    assert downstream.seen_request_id == "abc-123"
    assert start_header_values(sent, b"x-request-id") == [b"abc-123"]


def test_missing_id_generates_new_one() -> None:
    downstream = ContextProbeApp()

    sent = call_middleware(downstream, [])

    assert downstream.seen_request_id is not None
    assert REQUEST_ID_PATTERN.match(downstream.seen_request_id)
    # 响应头与 ContextVar 里是同一个 id，客户端可凭它报障定位日志。
    assert start_header_values(sent, b"x-request-id") == [
        downstream.seen_request_id.encode("latin-1")
    ]


def test_oversized_inbound_id_is_rejected_and_regenerated() -> None:
    too_long = "a" * (MAX_INBOUND_REQUEST_ID_LENGTH + 1)
    downstream = ContextProbeApp()

    sent = call_middleware(downstream, [(b"x-request-id", too_long.encode("latin-1"))])

    assert downstream.seen_request_id is not None
    assert downstream.seen_request_id != too_long
    assert REQUEST_ID_PATTERN.match(downstream.seen_request_id)
    assert start_header_values(sent, b"x-request-id") == [
        downstream.seen_request_id.encode("latin-1")
    ]


def test_control_char_inbound_id_is_rejected_and_regenerated() -> None:
    downstream = ContextProbeApp()

    sent = call_middleware(downstream, [(b"x-request-id", b"bad\nid")])

    assert downstream.seen_request_id is not None
    assert "\n" not in downstream.seen_request_id
    assert REQUEST_ID_PATTERN.match(downstream.seen_request_id)
    assert start_header_values(sent, b"x-request-id") == [
        downstream.seen_request_id.encode("latin-1")
    ]


def test_only_response_start_is_touched() -> None:
    """body 消息原样透传，头回写只发生在 http.response.start 上。"""
    downstream = ContextProbeApp()

    sent = call_middleware(downstream, [])

    assert response_start(sent)["type"] == "http.response.start"
    assert sent[1] == {"type": "http.response.body", "body": b"ok"}


def test_contextvar_is_reset_after_request() -> None:
    """请求结束（含下游异常）必须复位 ContextVar，后台日志不得挂旧 id。"""
    downstream = ContextProbeApp()
    call_middleware(downstream, [(b"x-request-id", b"abc-123")])

    # call_middleware 在同一协程内跑完中间件后返回，此时上下文应已复位。
    assert get_request_id() is None


def test_downstream_error_still_resets_contextvar() -> None:
    class ExplodingApp:
        async def __call__(self, scope: dict[str, Any], receive, send) -> None:
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        call_middleware(ExplodingApp(), [(b"x-request-id", b"abc-123")])

    assert get_request_id() is None


def test_non_http_scope_passes_through_untouched() -> None:
    """lifespan / websocket scope 直通，不注入 request id。"""
    downstream = ContextProbeApp()

    async def scenario() -> None:
        sent: list[dict[str, Any]] = []

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        async def receive() -> dict[str, Any]:
            return {"type": "lifespan.startup"}

        await RequestContextMiddleware(downstream)({"type": "lifespan"}, receive, send)

    asyncio.run(scenario())

    assert downstream.seen_request_id is None


def test_generate_request_id_shape() -> None:
    request_id = generate_request_id()

    assert REQUEST_ID_PATTERN.match(request_id)
    # 随机性抽查：两次生成的 id 不相同（16 hex 空间内碰撞概率可忽略）。
    assert generate_request_id() != request_id


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("abc-123", True),
        ("a" * MAX_INBOUND_REQUEST_ID_LENGTH, True),
        ("a" * (MAX_INBOUND_REQUEST_ID_LENGTH + 1), False),
        ("", False),
        ("bad\nid", False),
        ("tab\tid", False),
        ("req_中文", False),
    ],
)
def test_is_reusable_request_id(value: str, expected: bool) -> None:
    assert is_reusable_request_id(value) is expected


def test_ensure_request_id_from_scope_headers() -> None:
    scope = http_scope([(b"x-request-id", b" inbound-id ")])
    assert ensure_request_id(scope) == "inbound-id"

    assert REQUEST_ID_PATTERN.match(ensure_request_id(http_scope([])))


def test_log_filter_injects_request_id(caplog: pytest.LogCaptureFixture) -> None:
    """中间件上下文内打的日志，记录上带同一 request id（caplog 断言）。"""
    configure_request_id_logging()
    ContextProbeApp()

    class LoggingApp(ContextProbeApp):
        async def __call__(self, scope: dict[str, Any], receive, send) -> None:
            TEST_LOGGER.info("inside_request")
            await super().__call__(scope, receive, send)

    with caplog.at_level(logging.INFO, logger=TEST_LOGGER.name):
        call_middleware(LoggingApp(), [(b"x-request-id", b"abc-123")])

    assert caplog.records, "日志记录应被 caplog 捕获"
    assert all(record.request_id == "abc-123" for record in caplog.records)


def test_log_filter_uses_placeholder_without_request_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """无请求上下文（如启动期 / 后台任务）时占位 `-`，格式串不会缺属性。"""
    configure_request_id_logging()

    with caplog.at_level(logging.INFO, logger=TEST_LOGGER.name):
        TEST_LOGGER.info("outside_request")

    assert caplog.records
    assert all(record.request_id == "-" for record in caplog.records)


def test_sse_streaming_response_carries_request_id() -> None:
    """SSE 路径同样生效：响应头在开流前已发送，客户端能拿到 X-Request-ID。"""
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/stream")
    async def stream() -> StreamingResponse:
        async def events():
            yield b"data: hello\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    client = TestClient(app)
    with client.stream("GET", "/stream") as response:
        assert response.status_code == 200
        assert response.headers["x-request-id"].startswith("req_")
