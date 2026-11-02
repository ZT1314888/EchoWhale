from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from api.common.exceptions import ConfigurationError
from api.core.config import settings
from api.db.llm_usage_db import LlmUsageSink, build_llm_usage_sink
from api.integrations.llm.openai import OpenAICompatibleClient

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ProviderSlotConfig:
    """一个模型槽位（主/备）在 settings 里的完整配置。"""

    provider: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int


def provider_slot_from_settings(kind: str, slot: str) -> ProviderSlotConfig:
    """按 kind（text/vision）+ slot（primary/fallback）读取 settings 配置。"""
    prefix = f"{kind}_{slot}_"
    return ProviderSlotConfig(
        provider=getattr(settings, f"{prefix}provider"),
        base_url=getattr(settings, f"{prefix}base_url"),
        api_key=getattr(settings, f"{prefix}api_key"),
        model=getattr(settings, f"{prefix}model"),
        timeout_seconds=getattr(settings, f"{prefix}timeout_seconds"),
    )


def is_real_provider(provider: str) -> bool:
    """mock 或空值之外的 provider 名视为真实模型。"""
    return provider.strip().lower() not in {"", "mock"}


def resolve_engine_providers(
    *,
    kind: str,
    primary_slot: ProviderSlotConfig,
    fallback_slot: ProviderSlotConfig,
    build_mock: Callable[[], T],
    build_real: Callable[[ProviderSlotConfig], T],
) -> tuple[T, T]:
    """live/mock 分流与主备提升的共享解析。

    mock 模式下主备都返回 mock 实例；live 模式要求至少一个真实槽位，
    仅配置了回退槽位时会把回退提升为主。
    """
    if settings.model_runtime_mode.lower() != "live":
        primary = build_mock()
        return primary, build_mock()

    primary_real = is_real_provider(primary_slot.provider)
    fallback_real = is_real_provider(fallback_slot.provider)
    if not primary_real and not fallback_real:
        raise ConfigurationError(f"Live runtime requires at least one real {kind} provider")

    if primary_real:
        primary = build_real(primary_slot)
        fallback = build_real(fallback_slot) if fallback_real else primary
        return primary, fallback

    resolved = build_real(fallback_slot)
    return resolved, resolved


class TextCompletionProvider:
    """裸文本补全 provider，供不需要业务 prompt 组装的引擎（如反馈）复用。

    用量 sink 在构造期接入默认账本，调用方只需关心各自的 max_tokens 预算
    （feedback 引擎从 settings 读 llm_feedback_max_tokens 传入）。
    """

    def __init__(
        self,
        slot: ProviderSlotConfig,
        *,
        json_mode: bool = False,
        stream_include_usage: bool = False,
        max_tokens: int | None = None,
        usage_sink: LlmUsageSink | None = None,
    ) -> None:
        self._client = OpenAICompatibleClient(
            base_url=slot.base_url,
            api_key=slot.api_key,
            model=slot.model,
            timeout_seconds=slot.timeout_seconds,
            json_mode=json_mode,
            stream_include_usage=stream_include_usage,
            max_tokens=max_tokens,
            usage_sink=usage_sink if usage_sink is not None else build_llm_usage_sink(),
        )

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        return await self._client.async_complete_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
