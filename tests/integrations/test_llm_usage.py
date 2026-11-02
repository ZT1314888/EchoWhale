from __future__ import annotations

import logging

import httpx
import pytest

from api.integrations.llm.openai import OpenAICompatibleClient


class FakeUsageSink:
    """测试用同步 fake sink：按 Protocol 签名原样记录调用参数。"""

    def __init__(self) -> None:
        self.records: list[tuple[str, object, object, object]] = []

    def record(
        self,
        *,
        model: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
    ) -> None:
        self.records.append((model, prompt_tokens, completion_tokens, total_tokens))


class ExplodingSink:
    def record(self, *, model, prompt_tokens, completion_tokens, total_tokens) -> None:
        raise RuntimeError("sink is down")


def _transport_with_usage(usage: dict[str, object] | None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body: dict[str, object] = {"choices": [{"message": {"content": "Hello there!"}}]}
        if usage is not None:
            body["usage"] = usage
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


def test_complete_text_calls_sink_with_usage_fields() -> None:
    sink = FakeUsageSink()
    client = OpenAICompatibleClient(
        base_url="https://llm.test",
        api_key="key",
        model="demo-model",
        timeout_seconds=5,
        transport=_transport_with_usage(
            {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}
        ),
        usage_sink=sink,
    )

    text = client.complete_text(system_prompt="sys", user_prompt="usr")

    assert text == "Hello there!"
    assert sink.records == [("demo-model", 12, 3, 15)]


def test_sink_receives_none_for_missing_token_fields() -> None:
    """字段缺省容错：上游 usage 缺 token 字段时按 None 交给 sink，不抛错。"""
    sink = FakeUsageSink()
    client = OpenAICompatibleClient(
        base_url="https://llm.test",
        api_key="key",
        model="demo-model",
        timeout_seconds=5,
        transport=_transport_with_usage({"prompt_tokens": 12}),
        usage_sink=sink,
    )

    assert client.complete_text(system_prompt="sys", user_prompt="usr") == "Hello there!"
    assert sink.records == [("demo-model", 12, None, None)]


def test_complete_text_skips_sink_when_usage_absent() -> None:
    sink = FakeUsageSink()
    client = OpenAICompatibleClient(
        base_url="https://llm.test",
        api_key="key",
        model="demo-model",
        timeout_seconds=5,
        transport=_transport_with_usage(None),
        usage_sink=sink,
    )

    assert client.complete_text(system_prompt="sys", user_prompt="usr") == "Hello there!"
    assert sink.records == []


def test_sink_failure_does_not_break_completion(caplog) -> None:
    """sink 是旁路观测：抛错只降级为 llm_usage_sink_failed warning，主流程照常。"""
    client = OpenAICompatibleClient(
        base_url="https://llm.test",
        api_key="key",
        model="demo-model",
        timeout_seconds=5,
        transport=_transport_with_usage(
            {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}
        ),
        usage_sink=ExplodingSink(),
    )

    with caplog.at_level(logging.WARNING, logger="api.integrations.llm.openai"):
        text = client.complete_text(system_prompt="sys", user_prompt="usr")

    assert text == "Hello there!"
    assert "llm_usage_sink_failed" in caplog.text
    assert "demo-model" in caplog.text


def test_client_without_sink_still_logs_usage(caplog) -> None:
    """未注入 sink 时保留既有 logger 观测口径。"""
    client = OpenAICompatibleClient(
        base_url="https://llm.test",
        api_key="key",
        model="demo-model",
        timeout_seconds=5,
        transport=_transport_with_usage(
            {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}
        ),
    )

    with caplog.at_level(logging.INFO, logger="api.integrations.llm.openai"):
        assert client.complete_text(system_prompt="sys", user_prompt="usr") == "Hello there!"

    assert "llm_usage" in caplog.text
    assert "prompt_tokens=12" in caplog.text


@pytest.mark.anyio
async def test_async_completion_calls_sink_with_usage_fields() -> None:
    sink = FakeUsageSink()
    client = OpenAICompatibleClient(
        base_url="https://llm.test",
        api_key="key",
        model="demo-model",
        timeout_seconds=5,
        transport=_transport_with_usage(
            {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}
        ),
        usage_sink=sink,
    )

    text = await client.async_complete_text(system_prompt="sys", user_prompt="usr")

    assert text == "Hello there!"
    assert sink.records == [("demo-model", 12, 3, 15)]
