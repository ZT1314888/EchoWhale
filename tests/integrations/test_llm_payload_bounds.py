"""OpenAICompatibleClient 的 max_tokens 输出硬顶（Finding 10a）payload 断言。

构造期注入：非 None 时文本与图像 payload 都必须携带 max_tokens；
None 时不发送该字段，保持对不兼容网关的向后兼容。
"""

from __future__ import annotations

import json

import httpx

from api.integrations.llm.openai import OpenAICompatibleClient


def _capturing_transport(payloads: list[dict[str, object]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )

    return httpx.MockTransport(handler)


def _image_transport(payloads: list[dict[str, object]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": [{"type": "text", "text": "ok"}]}}]},
        )

    return httpx.MockTransport(handler)


def test_text_payload_includes_max_tokens_when_set() -> None:
    payloads: list[dict[str, object]] = []
    client = OpenAICompatibleClient(
        base_url="https://llm.test",
        api_key="key",
        model="demo-model",
        timeout_seconds=5,
        transport=_capturing_transport(payloads),
        max_tokens=300,
    )

    client.complete_text(system_prompt="sys", user_prompt="usr")

    assert payloads[0]["max_tokens"] == 300


def test_text_payload_omits_max_tokens_when_none() -> None:
    payloads: list[dict[str, object]] = []
    client = OpenAICompatibleClient(
        base_url="https://llm.test",
        api_key="key",
        model="demo-model",
        timeout_seconds=5,
        transport=_capturing_transport(payloads),
    )

    client.complete_text(system_prompt="sys", user_prompt="usr")

    assert "max_tokens" not in payloads[0]


def test_text_payload_keeps_max_tokens_alongside_json_mode() -> None:
    payloads: list[dict[str, object]] = []
    client = OpenAICompatibleClient(
        base_url="https://llm.test",
        api_key="key",
        model="demo-model",
        timeout_seconds=5,
        transport=_capturing_transport(payloads),
        json_mode=True,
        max_tokens=400,
    )

    client.complete_text(system_prompt="sys", user_prompt="usr")

    assert payloads[0]["max_tokens"] == 400
    assert payloads[0]["response_format"] == {"type": "json_object"}


def test_image_payload_includes_max_tokens_when_set() -> None:
    payloads: list[dict[str, object]] = []
    client = OpenAICompatibleClient(
        base_url="https://llm.test",
        api_key="key",
        model="demo-model",
        timeout_seconds=5,
        transport=_image_transport(payloads),
        max_tokens=500,
    )

    client.analyze_image(system_prompt="sys", user_prompt="usr", image_url="https://img.test/a.png")

    assert payloads[0]["max_tokens"] == 500


def test_image_payload_omits_max_tokens_when_none() -> None:
    payloads: list[dict[str, object]] = []
    client = OpenAICompatibleClient(
        base_url="https://llm.test",
        api_key="key",
        model="demo-model",
        timeout_seconds=5,
        transport=_image_transport(payloads),
    )

    client.analyze_image(system_prompt="sys", user_prompt="usr", image_url="https://img.test/a.png")

    assert "max_tokens" not in payloads[0]
