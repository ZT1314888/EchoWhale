from __future__ import annotations

from urllib.parse import urljoin

import httpx

from api.integrations.llm.base import BaseLLMClient
from api.integrations.llm.base import TextCompletionClient
from api.integrations.llm.base import VisionCompletionClient


class MockOpenAIClient(BaseLLMClient):
    def complete(self, prompt: str) -> str:
        return f"Mock completion for prompt: {prompt[:120]}"


class OpenAICompatibleClient(TextCompletionClient, VisionCompletionClient):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int = 30,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._transport = transport

    def complete_text(self, *, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        return self._post_chat_completion(payload)

    def analyze_image(self, *, system_prompt: str, user_prompt: str, image_url: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            "temperature": 0.1,
        }
        return self._post_chat_completion(payload)

    def _post_chat_completion(self, payload: dict[str, object]) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        with httpx.Client(timeout=self.timeout_seconds, transport=self._transport) as client:
            response = client.post(
                urljoin(self.base_url, "chat/completions"),
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            raise ValueError("Model response did not contain choices")

        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, list):
            text_chunks = [
                chunk.get("text", "")
                for chunk in content
                if isinstance(chunk, dict) and chunk.get("type") == "text"
            ]
            return "\n".join(part for part in text_chunks if part).strip()
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Model response did not contain textual content")
        return content.strip()
