from __future__ import annotations

from collections.abc import Iterator

import httpx
from fastapi.testclient import TestClient
import pytest

from api.integrations.deepgram.voice_agent import DeepgramThinkProxyTokenCodec
from api.main import app


@pytest.fixture(autouse=True)
def clear_overrides() -> Iterator[None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_deepgram_think_proxy_forwards_chat_completion_request(
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
        "api.routes.v1.deepgram.settings.deepgram_agent_think_timeout_seconds",
        45,
    )
    monkeypatch.setattr(
        "api.routes.v1.deepgram.settings.deepgram_agent_think_model",
        "qwen-plus",
    )
    captured: dict[str, object] = {}

    class FakeHttpxClient:
        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> httpx.Response:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-123",
                    "object": "chat.completion",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "Hello from the proxy.",
                            },
                        }
                    ],
                },
            )

    def build_client(timeout: int) -> FakeHttpxClient:
        captured["timeout"] = timeout
        return FakeHttpxClient()

    monkeypatch.setattr("api.routes.v1.deepgram._build_deepgram_async_client", build_client)
    token = DeepgramThinkProxyTokenCodec().issue("sess_123")

    response = client.post(
        "/api/v1/deepgram/think/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "model": "qwen-plus",
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Say hello."},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Hello from the proxy."
    assert captured == {
        "timeout": 45,
        "url": "https://gateway.example.com/v1/chat/completions",
        "headers": {
            "Content-Type": "application/json",
            "Authorization": "Bearer gateway-secret",
        },
        "json": {
            "model": "qwen-plus",
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Say hello."},
            ],
        },
    }


def test_deepgram_think_proxy_requires_bearer_token(client: TestClient) -> None:
    response = client.post(
        "/api/v1/deepgram/think/chat/completions",
        json={"model": "qwen-plus", "messages": []},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "message": "Proxy authorization required",
            "type": "authentication_error",
        }
    }


def test_deepgram_think_proxy_preserves_upstream_json_error_body(
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

    class FakeHttpxClient:
        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> httpx.Response:
            return httpx.Response(
                429,
                json={
                    "error": {
                        "message": "Rate limit exceeded",
                        "type": "rate_limit_error",
                    }
                },
            )

    monkeypatch.setattr(
        "api.routes.v1.deepgram._build_deepgram_async_client",
        lambda timeout: FakeHttpxClient(),
    )
    token = DeepgramThinkProxyTokenCodec().issue("sess_429")

    response = client.post(
        "/api/v1/deepgram/think/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={"model": "qwen-plus", "messages": []},
    )

    assert response.status_code == 429
    assert response.json() == {
        "error": {
            "message": "Rate limit exceeded",
            "type": "rate_limit_error",
        }
    }


def test_deepgram_think_proxy_rejects_invalid_request_payload(
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
    token = DeepgramThinkProxyTokenCodec().issue("sess_bad_json")

    response = client.post(
        "/api/v1/deepgram/think/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        content=b"{not-valid-json",
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "message": "Invalid proxy request payload",
            "type": "invalid_request_error",
        }
    }


def test_deepgram_think_proxy_rejects_model_mismatch(
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
        "gpt-4o-mini",
    )
    token = DeepgramThinkProxyTokenCodec().issue("sess_bad_model")

    response = client.post(
        "/api/v1/deepgram/think/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "model": "qwen-plus",
            "messages": [{"role": "user", "content": "Say hello."}],
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "message": "Requested model is not allowed for this proxy",
            "type": "invalid_request_error",
        }
    }


def test_deepgram_think_proxy_handles_non_json_upstream_response(
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

    class FakeHttpxClient:
        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> httpx.Response:
            return httpx.Response(502, text="<html>gateway failure</html>")

    monkeypatch.setattr(
        "api.routes.v1.deepgram._build_deepgram_async_client",
        lambda timeout: FakeHttpxClient(),
    )
    token = DeepgramThinkProxyTokenCodec().issue("sess_non_json")

    response = client.post(
        "/api/v1/deepgram/think/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={"model": "qwen-plus", "messages": []},
    )

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "message": "Deepgram think upstream returned a non-JSON response",
            "type": "upstream_invalid_response",
        }
    }


def test_deepgram_think_proxy_streams_sse_upstream_response(
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
    stream_body = (
        b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        b"data: [DONE]\n\n"
    )

    class FakeHttpxClient:
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

    def build_client(timeout: int) -> FakeHttpxClient:
        captured["timeout"] = timeout
        return FakeHttpxClient()

    monkeypatch.setattr("api.routes.v1.deepgram._build_deepgram_async_client", build_client)
    token = DeepgramThinkProxyTokenCodec().issue("sess_stream")

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
        "timeout": 30,
        "url": "https://gateway.example.com/v1/chat/completions",
        "headers": {
            "Content-Type": "application/json",
            "Authorization": "Bearer gateway-secret",
        },
        "json": {"model": "qwen-plus", "messages": [], "stream": True},
    }


def test_deepgram_think_proxy_preserves_json_error_body_for_stream_requests(
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

    class FakeHttpxClient:
        def build_request(
            self,
            method: str,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, object],
        ) -> httpx.Request:
            return httpx.Request(method, url, headers=headers, json=json)

        async def send(self, request: httpx.Request, *, stream: bool) -> httpx.Response:
            assert stream is True
            return httpx.Response(
                429,
                json={
                    "error": {
                        "message": "Rate limit exceeded",
                        "type": "rate_limit_error",
                    }
                },
                request=request,
            )

    monkeypatch.setattr(
        "api.routes.v1.deepgram._build_deepgram_async_client",
        lambda timeout: FakeHttpxClient(),
    )
    token = DeepgramThinkProxyTokenCodec().issue("sess_stream_error")

    response = client.post(
        "/api/v1/deepgram/think/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={"model": "qwen-plus", "messages": [], "stream": True},
    )

    assert response.status_code == 429
    assert response.json() == {
        "error": {
            "message": "Rate limit exceeded",
            "type": "rate_limit_error",
        }
    }
