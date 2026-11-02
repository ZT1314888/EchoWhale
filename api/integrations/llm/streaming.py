"""流式文本补全的传输层适配：SSE 分帧解析与本地降级流。

上游为 OpenAI 兼容 /chat/completions 的 stream=true SSE 响应；
部分兼容网关会忽略 stream 参数整包返回 JSON，此时降级为单 delta。
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DONE_SIGNAL = "[DONE]"


class TextStreamClosedError(RuntimeError):
    """流已被关闭后再次消费时抛出。"""


class SingleDeltaTextStream:
    """把整段文本包装成单 delta 流，供不支持流式路径的 provider 降级复用。"""

    def __init__(self, text: str) -> None:
        self._text = text
        self._consumed = False

    async def aiter_deltas(self) -> AsyncIterator[str]:
        if not self._consumed:
            self._consumed = True
            if self._text:
                yield self._text

    async def aclose(self) -> None:
        self._consumed = True


class WordChunkedTextStream:
    """把整段文本按词切分成多个 delta，模拟真实流式节奏（mock 模式与测试用）。"""

    def __init__(self, text: str) -> None:
        self._chunks = _split_word_chunks(text)
        self._consumed = False

    async def aiter_deltas(self) -> AsyncIterator[str]:
        if self._consumed:
            return
        self._consumed = True
        for chunk in self._chunks:
            yield chunk

    async def aclose(self) -> None:
        self._consumed = True


class HttpxTextStream:
    """持有已建立的 httpx 流式响应，把 SSE 帧解析成文本增量。

    failover 语义约定：打开（POST + 响应头校验）阶段抛出的异常可整体重试；
    一旦进入 aiter_deltas，中途断流直接向上传播，由调用方决定收尾。
    """

    def __init__(
        self,
        *,
        response: httpx.Response,
        owned_client: httpx.AsyncClient | None = None,
        record_usage: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._response = response
        self._owned_client = owned_client
        self._record_usage = record_usage
        self._closed = False

    async def aiter_deltas(self) -> AsyncIterator[str]:
        if self._closed:
            raise TextStreamClosedError("Text stream is already closed")
        buffer = ""
        try:
            async for raw_chunk in self._response.aiter_bytes():
                buffer += raw_chunk.decode("utf-8", errors="replace")
                while True:
                    frame, buffer = _split_sse_frame(buffer)
                    if frame is None:
                        break
                    payload = _parse_sse_data_payload(frame)
                    if payload is None:
                        continue
                    if payload == DONE_SIGNAL:
                        return
                    text, usage = _extract_stream_event(payload)
                    if usage is not None and self._record_usage is not None:
                        self._record_usage(usage)
                    if text:
                        yield text
        finally:
            await self.aclose()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._response.aclose()
        if self._owned_client is not None:
            await self._owned_client.aclose()


def _split_sse_frame(buffer: str) -> tuple[str | None, str]:
    """切出一个完整 SSE 事件帧（空行分隔），无完整帧时返回 None。"""
    for separator in ("\r\n\r\n", "\n\n"):
        index = buffer.find(separator)
        if index != -1:
            return buffer[:index], buffer[index + len(separator) :]
    return None, buffer


def _parse_sse_data_payload(frame: str) -> str | None:
    """提取帧内所有 data 行；注释行与仅含 event 字段的帧返回 None。"""
    data_lines: list[str] = []
    for raw_line in frame.splitlines():
        line = raw_line.rstrip("\r")
        if line.startswith("data:"):
            data_lines.append(line[len("data:") :].strip())
    if not data_lines:
        return None
    return "\n".join(data_lines)


def _extract_stream_event(payload: str) -> tuple[str | None, dict[str, Any] | None]:
    """从 data 载荷中提取文本增量与 usage；无法解析的帧静默跳过。"""
    try:
        chunk = json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("llm_stream_unparsable_frame payload_prefix=%s", payload[:120])
        return None, None
    if not isinstance(chunk, dict):
        return None, None

    usage = chunk.get("usage")
    normalized_usage = usage if isinstance(usage, dict) else None

    choices = chunk.get("choices")
    text: str | None = None
    if isinstance(choices, list) and choices:
        delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
        content = delta.get("content") if isinstance(delta, dict) else None
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
    return (text or None), normalized_usage


def _split_word_chunks(text: str) -> list[str]:
    """按空白切词并保留原间距，空文本返回空列表。"""
    chunks: list[str] = []
    remainder = text
    while True:
        leading, separator, rest = remainder.partition(" ")
        if not separator:
            if leading:
                chunks.append(leading)
            return chunks
        chunks.append(leading + " ")
        remainder = rest
