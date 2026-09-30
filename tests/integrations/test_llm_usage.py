from __future__ import annotations

import httpx

from api.integrations.llm.openai import OpenAICompatibleClient


def _transport_with_usage() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Hello there!"}}],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 3,
                    "total_tokens": 15,
                },
            },
        )

    return httpx.MockTransport(handler)


def test_extract_content_records_usage_with_injected_recorder() -> None:
    records: list[tuple[str, dict[str, object]]] = []
    client = OpenAICompatibleClient(
        base_url="https://llm.test",
        api_key="key",
        model="demo-model",
        timeout_seconds=5,
        transport=_transport_with_usage(),
        usage_recorder=lambda model, usage: records.append((model, usage)),
    )

    text = client.complete_text(system_prompt="sys", user_prompt="usr")

    assert text == "Hello there!"
    assert records == [
        (
            "demo-model",
            {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
        )
    ]


def test_extract_content_skips_usage_when_absent() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Hi"}}]},
        )

    records: list[tuple[str, dict[str, object]]] = []
    client = OpenAICompatibleClient(
        base_url="https://llm.test",
        api_key="key",
        model="demo-model",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
        usage_recorder=lambda model, usage: records.append((model, usage)),
    )

    assert client.complete_text(system_prompt="sys", user_prompt="usr") == "Hi"
    assert records == []
