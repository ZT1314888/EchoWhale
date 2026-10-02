"""教练回复流式链路直测：provider 流 + agent failover。"""

from __future__ import annotations

import json

import httpx
import pytest

from api.core.config import settings
from api.integrations.llm.openai import OpenAICompatibleClient
from api.integrations.llm.streaming import SingleDeltaTextStream
from api.modules.coach_engine.agent import CoachEngineAgent
from api.modules.coach_engine.providers.chat_provider import (
    MockChatProvider,
    OpenAICompatibleChatProvider,
)
from api.modules.coach_engine.schema import CoachReplyInput


def _payload() -> CoachReplyInput:
    return CoachReplyInput(
        scene="coffee_shop",
        role="barista",
        learner_message="I want a latte",
        visual_anchors=["counter", "menu"],
        vocab_candidates=["latte"],
        recent_messages=[],
    )


def _sse_transport(body: bytes, status_code: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if status_code >= 400:
            return httpx.Response(status_code, json={"error": {"message": "upstream down"}})
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    return httpx.MockTransport(handler)


@pytest.mark.anyio
async def test_mock_chat_provider_streams_word_chunks() -> None:
    provider = MockChatProvider()
    stream = await provider.open_reply_stream(_payload())
    deltas = [delta async for delta in stream.aiter_deltas()]

    assert len(deltas) > 1
    assert "".join(deltas) == (await provider.reply(_payload())).text


@pytest.mark.anyio
async def test_openai_chat_provider_streams_reply_deltas(monkeypatch) -> None:
    monkeypatch.setattr(settings, "model_runtime_mode", "live")
    body = (
        b'data: {"choices":[{"delta":{"content":"Sure, "}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":"one latte."}}]}\n\n'
        b"data: [DONE]\n\n"
    )
    provider = OpenAICompatibleChatProvider(
        base_url="https://llm.test/v1",
        api_key="key",
        model="m",
        timeout_seconds=5,
    )
    provider.client = OpenAICompatibleClient(
        base_url="https://llm.test/v1/",
        api_key="key",
        model="m",
        timeout_seconds=5,
        transport=_sse_transport(body),
    )
    stream = await provider.open_reply_stream(_payload())
    assert "".join([delta async for delta in stream.aiter_deltas()]) == "Sure, one latte."


@pytest.mark.anyio
async def test_agent_stream_reply_falls_back_to_backup_provider() -> None:
    class ExplodingProvider:
        async def reply(self, payload: CoachReplyInput):
            raise AssertionError("reply must not be called when stream opens first")

        async def open_reply_stream(self, payload: CoachReplyInput):
            raise httpx.ConnectError("primary down")

    provider = MockChatProvider()
    agent = CoachEngineAgent(primary_provider=ExplodingProvider(), fallback_provider=provider)

    stream = await agent.stream_reply(_payload())
    deltas = [delta async for delta in stream.aiter_deltas()]

    assert "".join(deltas) == (await provider.reply(_payload())).text


@pytest.mark.anyio
async def test_agent_stream_reply_degrades_reply_only_provider_to_single_delta() -> None:
    class ReplyOnlyProvider:
        async def reply(self, payload: CoachReplyInput):
            from api.modules.coach_engine.schema import CoachReplyResult

            return CoachReplyResult(text="whole reply at once")

    agent = CoachEngineAgent(primary_provider=ReplyOnlyProvider())
    stream = await agent.stream_reply(_payload())

    assert isinstance(stream, SingleDeltaTextStream)
    assert [delta async for delta in stream.aiter_deltas()] == ["whole reply at once"]


@pytest.mark.anyio
async def test_agent_stream_reply_raises_composed_failure_when_all_open_fail() -> None:
    class DownProvider:
        async def reply(self, payload: CoachReplyInput):
            raise AssertionError("must not be reached")

        async def open_reply_stream(self, payload: CoachReplyInput):
            raise httpx.ConnectError("down")

    agent = CoachEngineAgent(primary_provider=DownProvider(), fallback_provider=DownProvider())

    from api.common.exceptions import ModelProviderError

    with pytest.raises(ModelProviderError):
        await agent.stream_reply(_payload())


def _unused_json_guard() -> None:  # pragma: no cover - keep json import meaningful
    json.dumps({})
