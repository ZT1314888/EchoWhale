from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol


class TextCompletionClient(Protocol):
    def complete_text(self, *, system_prompt: str, user_prompt: str) -> str: ...
    async def async_complete_text(self, *, system_prompt: str, user_prompt: str) -> str: ...


class TextStream(Protocol):
    """一次已打开的增量文本流：迭代前不产生网络 IO，中途断流直接抛错。"""

    def aiter_deltas(self) -> AsyncIterator[str]: ...
    async def aclose(self) -> None: ...


class StreamingTextCompletionClient(Protocol):
    """可选能力协议：打开即校验完成的流式文本补全客户端。"""

    async def async_open_text_stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> TextStream: ...


class VisionCompletionClient(Protocol):
    def analyze_image(self, *, system_prompt: str, user_prompt: str, image_url: str) -> str: ...
    async def async_analyze_image(self, *, system_prompt: str, user_prompt: str, image_url: str) -> str: ...
