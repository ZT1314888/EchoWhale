from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.common.middleware import BodySizeLimitMiddleware


class RecordingApp:
    """下游替身：记录是否被调用、收到多少 body，并把 body 原样回显。"""

    def __init__(self) -> None:
        self.called = False
        self.seen_scopes: list[dict[str, Any]] = []
        self.received = b""

    async def __call__(self, scope: dict[str, Any], receive, send) -> None:
        self.called = True
        self.seen_scopes.append(scope)
        if scope["type"] == "http":
            while True:
                message = await receive()
                if message["type"] != "http.request":
                    break
                self.received += message.get("body", b"")
                if not message.get("more_body", False):
                    break
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})


def http_scope(headers: list[tuple[bytes, bytes]]) -> dict[str, Any]:
    return {"type": "http", "method": "POST", "path": "/x", "headers": headers}


def scripted_receive(chunks: list[bytes]):
    messages: list[dict[str, Any]] = [
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ]

    async def receive() -> dict[str, Any]:
        return messages.pop(0)

    return receive


async def collect_send() -> tuple[list[dict[str, Any]], Any]:
    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    return sent, send


def response_body_json(sent: list[dict[str, Any]]) -> dict[str, Any]:
    body = b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body"
    )
    return json.loads(body)


def test_declared_content_length_over_cap_rejected_before_downstream() -> None:
    """头部声明超限：不读 body、下游 handler 完全不执行，直接回 413 统一信封。"""
    downstream = RecordingApp()
    middleware = BodySizeLimitMiddleware(downstream, max_body_bytes=1024)
    sent, send = asyncio.run(collect_send())

    asyncio.run(
        middleware(
            http_scope([(b"content-length", b"2048")]),
            scripted_receive([b"x" * 2048]),
            send,
        )
    )

    assert downstream.called is False
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413
    # 信封与 ApiResponse.failed（body_code=FileTooLargeError.code=1001）同构。
    assert response_body_json(sent) == {"code": 1001, "message": "Request body too large"}


def test_declared_content_length_within_cap_passes_through() -> None:
    downstream = RecordingApp()
    middleware = BodySizeLimitMiddleware(downstream, max_body_bytes=1024)
    sent, send = asyncio.run(collect_send())

    asyncio.run(
        middleware(
            http_scope([(b"content-length", b"4")]),
            scripted_receive([b"abcd"]),
            send,
        )
    )

    assert downstream.called is True
    assert downstream.received == b"abcd"
    assert sent[0]["status"] == 200


def test_streamed_body_over_cap_is_cut_and_returns_413() -> None:
    """chunked 超限：不再向下游转发剩余 chunk，先发 413 再停止消费。"""
    downstream = RecordingApp()
    middleware = BodySizeLimitMiddleware(downstream, max_body_bytes=1024)
    sent, send = asyncio.run(collect_send())

    # 两个 chunk：累计 640 + 640 超过 cap=1024，第二块在计数后即被截断。
    asyncio.run(
        middleware(
            http_scope([]),  # 无 Content-Length，走流式计数路径
            scripted_receive([b"a" * 640, b"b" * 640]),
            send,
        )
    )

    assert downstream.called is True
    # 下游只拿到第一个 chunk，超限的第二个 chunk 未被转发。
    assert downstream.received == b"a" * 640
    assert sent[0]["status"] == 413
    assert response_body_json(sent) == {"code": 1001, "message": "Request body too large"}


def test_streamed_body_within_cap_passes_through() -> None:
    downstream = RecordingApp()
    middleware = BodySizeLimitMiddleware(downstream, max_body_bytes=1024)
    sent, send = asyncio.run(collect_send())

    asyncio.run(middleware(http_scope([]), scripted_receive([b"abc", b"def"]), send))

    assert downstream.called is True
    assert downstream.received == b"abcdef"
    assert sent[0]["status"] == 200


def test_non_http_scope_passes_through_untouched() -> None:
    """lifespan / websocket scope 直通，不参与 body 大小管理。"""
    downstream = RecordingApp()
    middleware = BodySizeLimitMiddleware(downstream, max_body_bytes=1024)
    lifespan_scope = {"type": "lifespan"}

    async def receive() -> dict[str, Any]:
        return {"type": "lifespan.startup"}

    async def send(message: dict[str, Any]) -> None: ...

    asyncio.run(middleware(lifespan_scope, receive, send))

    assert downstream.called is True
    assert downstream.seen_scopes == [lifespan_scope]


def test_invalid_content_length_falls_back_to_streaming_path() -> None:
    """非法 Content-Length 不拦截：按无声明处理，交由框架解析报错。"""
    downstream = RecordingApp()
    middleware = BodySizeLimitMiddleware(downstream, max_body_bytes=1024)
    sent, send = asyncio.run(collect_send())

    asyncio.run(
        middleware(
            http_scope([(b"content-length", b"not-a-number")]),
            scripted_receive([b"hello"]),
            send,
        )
    )

    assert downstream.called is True
    assert downstream.received == b"hello"
    assert sent[0]["status"] == 200


def test_middleware_on_real_app_rejects_oversized_http_body() -> None:
    """走真实 HTTP 栈（add_middleware 挂载 + TestClient）验证 413 信封可被客户端正常解析。"""
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware, max_body_bytes=64)

    @app.post("/echo")
    def echo() -> dict[str, str]:
        return {"ok": "yes"}

    client = TestClient(app)

    oversized = client.post("/echo", content=b"x" * 100)
    assert oversized.status_code == 413
    assert oversized.json() == {"code": 1001, "message": "Request body too large"}

    # 正常大小请求不受影响。
    ok = client.post("/echo", content=b"x" * 10)
    assert ok.status_code == 200
    assert ok.json() == {"ok": "yes"}
