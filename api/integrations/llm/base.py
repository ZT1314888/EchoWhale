from __future__ import annotations

from typing import Protocol


class BaseLLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...


class TextCompletionClient(Protocol):
    def complete_text(self, *, system_prompt: str, user_prompt: str) -> str: ...


class VisionCompletionClient(Protocol):
    def analyze_image(self, *, system_prompt: str, user_prompt: str, image_url: str) -> str: ...
