from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from api.db.session_db import build_session_repository
from api.integrations.deepgram.voice_agent import DeepgramThinkProxyTokenCodec
from api.main import app
from api.services.llm_rate_limit import InMemoryLLMRateLimiter, get_llm_rate_limiter
from tests.api.test_deepgram_routes import StubSessionHeadRepository


@pytest.fixture(autouse=True)
def clear_overrides() -> Iterator[None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    # 既有用例的令牌 sid 都视为已存在会话；限流器用默认规则的内存实现。
    app.dependency_overrides[build_session_repository] = lambda: StubSessionHeadRepository()
    app.dependency_overrides[get_llm_rate_limiter] = lambda: InMemoryLLMRateLimiter()
    with TestClient(app) as test_client:
        yield test_client


def test_async_deepgram_proxy_forwards_json_request(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "api.routes.v1.deepgram.settings.deepgram_agent_think_upstream_base_url",
        "https://gateway.example.com/v1",
    )
    monkeypatch.setattr(
        "api.routes.v1.deepgram.settings.deepgram_agent_think_upstream_api_key",
        "gateway-secret",
    )
    monkeypatch.setattr(
        "api.routes.v1.deepgram.settings.deepgram_agent_think_model",
        "qwen-plus",
    )

    captured: dict[str, object] = {}

    class FakeAsyncClient:
        async def post(
            self, url: str, *, headers: dict[str, str], json: dict[str, object]
        ) -> httpx.Response:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "Hello from async proxy.",
                            }
                        }
                    ]
                },
            )

    monkeypatch.setattr(
        "api.routes.v1.deepgram._get_deepgram_async_client",
        lambda: FakeAsyncClient(),
    )
    token = DeepgramThinkProxyTokenCodec().issue("sess_async_json")

    response = client.post(
        "/api/v1/deepgram/think/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "model": "qwen-plus",
            "messages": [{"role": "user", "content": "Say hello."}],
        },
    )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Hello from async proxy."
    assert captured == {
        "url": "https://gateway.example.com/v1/chat/completions",
        "headers": {
            "Content-Type": "application/json",
            "Authorization": "Bearer gateway-secret",
        },
        "json": {
            "model": "qwen-plus",
            "messages": [{"role": "user", "content": "Say hello."}],
        },
    }


def test_async_deepgram_proxy_streams_sse_response(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "api.routes.v1.deepgram.settings.deepgram_agent_think_upstream_base_url",
        "https://gateway.example.com/v1",
    )
    monkeypatch.setattr(
        "api.routes.v1.deepgram.settings.deepgram_agent_think_upstream_api_key",
        "gateway-secret",
    )
    monkeypatch.setattr(
        "api.routes.v1.deepgram.settings.deepgram_agent_think_model",
        "qwen-plus",
    )

    captured: dict[str, object] = {}
    stream_body = b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n' b"data: [DONE]\n\n"

    class FakeAsyncClient:
        def build_request(
            self,
            method: str,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, object],
        ) -> httpx.Request:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return httpx.Request(method, url, headers=headers, json=json)

        async def send(self, request: httpx.Request, *, stream: bool) -> httpx.Response:
            assert stream is True
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                content=stream_body,
                request=request,
            )

    monkeypatch.setattr(
        "api.routes.v1.deepgram._get_deepgram_async_client",
        lambda: FakeAsyncClient(),
    )
    token = DeepgramThinkProxyTokenCodec().issue("sess_async_stream")

    with client.stream(
        "POST",
        "/api/v1/deepgram/think/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={"model": "qwen-plus", "messages": [], "stream": True},
    ) as response:
        body = response.read().decode("utf-8")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'data: {"choices":[{"delta":{"content":"Hello"}}]}' in body
    assert "data: [DONE]" in body
    assert captured == {
        "url": "https://gateway.example.com/v1/chat/completions",
        "headers": {
            "Content-Type": "application/json",
            "Authorization": "Bearer gateway-secret",
        },
        "json": {"model": "qwen-plus", "messages": [], "stream": True},
    }
