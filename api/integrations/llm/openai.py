from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any
from urllib.parse import urljoin

import httpx

from api.common.telemetry import stamp_llm_model, stamp_llm_usage
from api.integrations.llm.base import TextCompletionClient, VisionCompletionClient
from api.integrations.llm.streaming import HttpxTextStream, SingleDeltaTextStream

logger = logging.getLogger(__name__)


class OpenAICompatibleClient(TextCompletionClient, VisionCompletionClient):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int = 30,
        transport: httpx.BaseTransport | None = None,
        usage_sink=None,
        json_mode: bool = False,
        stream_include_usage: bool = False,
        max_tokens: int | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._transport = transport
        self._usage_sink = usage_sink
        self._json_mode = json_mode
        self._stream_include_usage = stream_include_usage
        # 输出硬顶（Finding 10a）：构造期注入而非每调用传参，保证同一客户端
        # 的所有请求预算一致；None 时不发送字段，保持向后兼容。
        self._max_tokens = max_tokens

    def complete_text(self, *, system_prompt: str, user_prompt: str) -> str:
        payload = self._build_text_payload(system_prompt, user_prompt)
        return self._post_chat_completion(payload)

    async def async_complete_text(self, *, system_prompt: str, user_prompt: str) -> str:
        payload = self._build_text_payload(system_prompt, user_prompt)
        return await self._async_post_chat_completion(payload)

    async def async_open_text_stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> HttpxTextStream | SingleDeltaTextStream:
        """打开一条流式文本补全：连接与状态码校验完成后才返回，供 failover 重试。

        上游忽略 stream 参数整包返回 JSON 时，降级为单 delta 流，避免浪费已计费的调用。
        """
        payload = self._build_text_payload(system_prompt, user_prompt)
        payload["stream"] = True
        if self._stream_include_usage:
            payload["stream_options"] = {"include_usage": True}

        if self._transport is not None:
            client = httpx.AsyncClient(timeout=self.timeout_seconds, transport=self._transport)
            owned_client: httpx.AsyncClient | None = client
        else:
            client = _get_shared_async_client(self.timeout_seconds)
            owned_client = None

        try:
            request = client.build_request(
                "POST",
                urljoin(self.base_url, "chat/completions"),
                headers=self._get_headers(),
                json=payload,
            )
            response = await client.send(request, stream=True)
        except BaseException:
            if owned_client is not None:
                await owned_client.aclose()
            raise

        if response.status_code >= 400:
            try:
                await response.aread()
            finally:
                await response.aclose()
                if owned_client is not None:
                    await owned_client.aclose()
            response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if not _is_sse_content_type(content_type):
            try:
                body = await response.aread()
            finally:
                await response.aclose()
                if owned_client is not None:
                    await owned_client.aclose()
            # JSONDecodeError 是 ValueError 子类，与整包路径一样属于可重试的解析失败。
            data = json.loads(body)
            return SingleDeltaTextStream(self._extract_content(data))

        return HttpxTextStream(
            response=response,
            owned_client=owned_client,
            record_usage=self._record_stream_usage,
        )

    def _build_text_payload(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
        # 全部 5 个公开方法先经 payload builder：模型名 stamp 覆盖在此即覆盖全部入口。
        stamp_llm_model(self.model)
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        if self._max_tokens is not None:
            payload["max_tokens"] = self._max_tokens
        if self._json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def analyze_image(self, *, system_prompt: str, user_prompt: str, image_url: str) -> str:
        payload = self._build_image_payload(system_prompt, user_prompt, image_url)
        return self._post_chat_completion(payload)

    async def async_analyze_image(
        self, *, system_prompt: str, user_prompt: str, image_url: str
    ) -> str:
        payload = self._build_image_payload(system_prompt, user_prompt, image_url)
        return await self._async_post_chat_completion(payload)

    def _build_image_payload(
        self, system_prompt: str, user_prompt: str, image_url: str
    ) -> dict[str, object]:
        stamp_llm_model(self.model)
        payload: dict[str, object] = {
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
        if self._max_tokens is not None:
            payload["max_tokens"] = self._max_tokens
        return payload

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _post_chat_completion(self, payload: dict[str, object]) -> str:
        headers = self._get_headers()
        if self._transport is not None:
            with httpx.Client(timeout=self.timeout_seconds, transport=self._transport) as client:
                response = client.post(
                    urljoin(self.base_url, "chat/completions"),
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
        else:
            response = _get_shared_sync_client(self.timeout_seconds).post(
                urljoin(self.base_url, "chat/completions"),
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

        data = response.json()
        return self._extract_content(data)

    async def _async_post_chat_completion(self, payload: dict[str, object]) -> str:
        headers = self._get_headers()
        if self._transport is not None:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self._transport
            ) as client:
                response = await client.post(
                    urljoin(self.base_url, "chat/completions"),
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
        else:
            response = await _get_shared_async_client(self.timeout_seconds).post(
                urljoin(self.base_url, "chat/completions"),
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

        data = response.json()
        return self._extract_content(data)

    def _extract_content(self, data: dict[str, Any]) -> str:
        choices = data.get("choices", [])
        if not choices:
            raise ValueError("Model response did not contain choices")

        self._record_usage(data)

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

    def _record_usage(self, data: dict[str, Any]) -> None:
        """记录上游 usage 字段；无 usage 时静默跳过。

        顺序固定：先 logger（保留既有观测口径）后 sink；整包 `_record_usage`
        与流式 `_record_stream_usage` 共用本路径，口径一致。sink 是旁路观测
        而非业务依赖：任一异常只降级为 warning，绝不影响补全主流程。
        """
        usage = data.get("usage")
        if not isinstance(usage, dict):
            return
        logger.info(
            "llm_usage model=%s prompt_tokens=%s completion_tokens=%s total_tokens=%s",
            self.model,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            usage.get("total_tokens"),
        )
        # token 三元组顺手富集到当时活跃 span（整包路径 = llm.attempt；流式路径
        # usage 在流末帧到达，落在当时活跃的 engine/server span，见 design 2.4）。
        stamp_llm_usage(
            self.model,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
        if self._usage_sink is None:
            return
        # 字段缺省容错：上游 usage 任一 token 字段缺失按 None 交给 sink。
        try:
            self._usage_sink.record(
                model=self.model,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
            )
        except Exception as exc:  # noqa: BLE001 - sink 失败必须与主流程隔离并记 warning
            logger.warning(
                "llm_usage_sink_failed model=%s error=%s: %s", self.model, type(exc).__name__, exc
            )

    def _record_stream_usage(self, usage: dict[str, Any]) -> None:
        """流式末帧的 usage 以原始 dict 上报，与整包路径共用落点。"""
        self._record_usage({"usage": usage})


@lru_cache(maxsize=8)
def _get_shared_sync_client(timeout_seconds: int) -> httpx.Client:
    return httpx.Client(timeout=timeout_seconds)


@lru_cache(maxsize=8)
def _get_shared_async_client(timeout_seconds: int) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout_seconds)


def _is_sse_content_type(content_type: str) -> bool:
    return content_type.split(";", 1)[0].strip().lower() == "text/event-stream"
