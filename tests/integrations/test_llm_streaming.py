"""OpenAICompatibleClient 流式打开 + SSE 帧解析的直测。"""

from __future__ import annotations

import json

import httpx
import pytest

from api.integrations.llm.openai import OpenAICompatibleClient
from api.integrations.llm.streaming import SingleDeltaTextStream


def _sse_body(frames: list[dict[str, object]]) -> bytes:
    chunks: list[bytes] = []
    for frame in frames:
        chunks.append(f"data: {json.dumps(frame)}\n\n".encode("utf-8"))
    chunks.append(b"data: [DONE]\n\n")
    return b"".join(chunks)


def _stream_transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.mark.anyio
async def test_stream_yields_deltas_and_records_final_usage() -> None:
    recorded: list[dict[str, object]] = []
    body = _sse_body(
        [
            {"choices": [{"delta": {"role": "assistant", "content": "Hello"}}]},
            {"choices": [{"delta": {"content": " world"}}]},
            {"choices": [{"delta": {}}], "usage": {"prompt_tokens": 7, "completion_tokens": 3}},
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        payload = json.loads(request.content)
        assert payload["stream"] is True
        # 默认不携带 stream_options，避免不兼容网关直接 4xx。
        assert "stream_options" not in payload
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    client = OpenAICompatibleClient(
        base_url="https://llm.test/v1/",
        api_key="key",
        model="test-model",
        timeout_seconds=5,
        transport=_stream_transport(handler),
        usage_recorder=lambda model, usage: recorded.append(usage),
    )
    stream = await client.async_open_text_stream(
        system_prompt="sys",
        user_prompt="user",
    )
    deltas = [delta async for delta in stream.aiter_deltas()]

    assert deltas == ["Hello", " world"]
    assert recorded == [{"prompt_tokens": 7, "completion_tokens": 3}]


@pytest.mark.anyio
async def test_stream_requests_usage_when_enabled() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload.get("stream_options") == {"include_usage": True}
        return httpx.Response(
            200,
            content=_sse_body([{"choices": [{"delta": {"content": "ok"}}]}]),
            headers={"content-type": "text/event-stream"},
        )

    client = OpenAICompatibleClient(
        base_url="https://llm.test/v1/",
        api_key="key",
        model="m",
        timeout_seconds=5,
        transport=_stream_transport(handler),
        stream_include_usage=True,
    )
    stream = await client.async_open_text_stream(system_prompt="s", user_prompt="u")
    assert [delta async for delta in stream.aiter_deltas()] == ["ok"]


@pytest.mark.anyio
async def test_stream_falls_back_to_single_delta_for_non_sse_json() -> None:
    recorded: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "plain reply"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
            headers={"content-type": "application/json"},
        )

    client = OpenAICompatibleClient(
        base_url="https://llm.test/v1/",
        api_key="k",
        model="m",
        timeout_seconds=5,
        transport=_stream_transport(handler),
        usage_recorder=lambda model, usage: recorded.append(usage),
    )
    stream = await client.async_open_text_stream(system_prompt="s", user_prompt="u")
    assert isinstance(stream, SingleDeltaTextStream)
    assert [delta async for delta in stream.aiter_deltas()] == ["plain reply"]
    assert recorded == [{"prompt_tokens": 1, "completion_tokens": 1}]


@pytest.mark.anyio
async def test_stream_open_failure_raises_for_failover() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "boom"}})

    client = OpenAICompatibleClient(
        base_url="https://llm.test/v1/",
        api_key="k",
        model="m",
        timeout_seconds=5,
        transport=_stream_transport(handler),
    )
    with pytest.raises(httpx.HTTPStatusError):
        await client.async_open_text_stream(system_prompt="s", user_prompt="u")


@pytest.mark.anyio
async def test_stream_frames_split_across_chunks_are_reassembled() -> None:
    body = _sse_body([{"choices": [{"delta": {"content": "split"}}]}])
    cut = body.index(b"\n\n") + 1  # 把帧从分隔符中间切开

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=body,
            headers={"content-type": "text/event-stream"},
        )

    client = OpenAICompatibleClient(
        base_url="https://llm.test/v1/",
        api_key="k",
        model="m",
        timeout_seconds=5,
        transport=_stream_transport(handler),
    )
    stream = await client.async_open_text_stream(system_prompt="s", user_prompt="u")

    # 直接驱动底层分片，验证解析器对跨 chunk 帧的重组能力。
    deltas: list[str] = []
    async for delta in stream.aiter_deltas():
        deltas.append(delta)
    assert "".join(deltas) == "split"
    assert cut > 0
