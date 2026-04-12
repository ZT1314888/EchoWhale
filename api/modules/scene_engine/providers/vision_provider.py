from __future__ import annotations

import json
from typing import Protocol

import httpx

from api.common.exceptions import ConfigurationError
from api.common.exceptions import ModelProviderError
from api.core.config import settings
from api.integrations.llm.openai import OpenAICompatibleClient
from api.modules.scene_engine.prompts.scene_prompts import SCENE_INFERENCE_PROMPT
from api.modules.scene_engine.schema import SceneAnalysisInput, SceneAnalysisResult
from api.modules.scene_engine.tools.image_tools import infer_tags_from_filename


class VisionProvider(Protocol):
    async def analyze(self, payload: SceneAnalysisInput) -> SceneAnalysisResult: ...


class MockVisionProvider:
    async def analyze(self, payload: SceneAnalysisInput) -> SceneAnalysisResult:
        """根据文件名弱规则生成稳定假数据，方便本地开发和测试。"""
        filename = payload.filename.lower()
        filename_tags = infer_tags_from_filename(payload.filename)

        if any(token in filename for token in ("coffee", "cafe", "latte")):
            return SceneAnalysisResult(
                scene="coffee_shop",
                role="barista",
                opener="Hi there, what can I get started for you today?",
                visual_anchors=["counter", "menu board"],
                vocab_candidates=_merge_vocab_candidates(
                    filename_tags,
                    ["latte", "order", "size"],
                ),
                confidence=0.83,
            )
        if any(token in filename for token in ("office", "desk", "meeting")):
            return SceneAnalysisResult(
                scene="office",
                role="office staff",
                opener="Hello! Welcome to our office. Are you here for a meeting or a visit today?",
                visual_anchors=["glass wall", "logo", "sofa"],
                vocab_candidates=_merge_vocab_candidates(
                    filename_tags,
                    ["visitor", "meeting", "reception"],
                ),
                confidence=0.78,
            )
        if any(token in filename for token in ("street", "travel", "station")):
            return SceneAnalysisResult(
                scene="travel",
                role="local_guide",
                opener="You look a little lost. Where are you trying to go?",
                visual_anchors=["platform sign", "ticket gate"],
                vocab_candidates=_merge_vocab_candidates(
                    filename_tags,
                    ["ticket", "platform", "direction"],
                ),
                confidence=0.74,
            )

        return SceneAnalysisResult(
            scene="restaurant",
            role="server",
            opener="Welcome in. Have you decided what you'd like to order?",
            visual_anchors=["dining table", "menu stand"],
            vocab_candidates=_merge_vocab_candidates(
                filename_tags,
                ["order", "dish", "recommendation"],
            ),
            confidence=0.71,
        )


class OpenAICompatibleVisionProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
    ) -> None:
        """保存远端视觉模型调用所需的客户端配置。"""
        self.client = OpenAICompatibleClient(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
        )

    async def analyze(self, payload: SceneAnalysisInput) -> SceneAnalysisResult:
        """调用兼容 OpenAI 的视觉模型，并把返回值收敛成统一 schema。"""
        user_prompt = (
            "Return one JSON object for this image. "
            f"Filename hint (weak): {payload.filename}"
        )
        try:
            raw = await self.client.async_analyze_image(
                system_prompt=SCENE_INFERENCE_PROMPT,
                user_prompt=user_prompt,
                image_url=payload.media_url,
            )
            return SceneAnalysisResult.model_validate(_load_json(raw))
        except httpx.TimeoutException as exc:  # pragma: no cover - live provider path
            raise ModelProviderError("Vision provider timed out") from exc
        except httpx.HTTPStatusError as exc:  # pragma: no cover - live provider path
            status_code = exc.response.status_code
            if 400 <= status_code < 500:
                raise ModelProviderError(
                    f"Vision provider rejected request with status {status_code}"
                ) from exc
            raise ModelProviderError(
                f"Vision provider failed with status {status_code}"
            ) from exc
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:  # pragma: no cover
            raise ModelProviderError("Vision provider failed to analyze image") from exc
        except Exception as exc:  # pragma: no cover - live provider path
            raise ModelProviderError("Vision provider failed to analyze image") from exc


def build_primary_vision_provider() -> VisionProvider:
    """按主配置构造视觉 provider。"""
    return _build_provider(
        provider=settings.vision_primary_provider,
        base_url=settings.vision_primary_base_url,
        api_key=settings.vision_primary_api_key,
        model=settings.vision_primary_model,
        timeout_seconds=settings.vision_primary_timeout_seconds,
    )


def build_fallback_vision_provider() -> VisionProvider:
    """按回退配置构造视觉 provider。"""
    return _build_provider(
        provider=settings.vision_fallback_provider,
        base_url=settings.vision_fallback_base_url,
        api_key=settings.vision_fallback_api_key,
        model=settings.vision_fallback_model,
        timeout_seconds=settings.vision_fallback_timeout_seconds,
    )


def has_real_vision_provider(provider: str) -> bool:
    """判断当前 provider 配置是否真的会走远端模型。"""
    return provider.strip().lower() not in {"", "mock"}


def _build_provider(
    *,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    timeout_seconds: int,
) -> VisionProvider:
    """根据运行模式和配置选择 mock 或真实视觉 provider。"""
    normalized = provider.strip().lower()
    if settings.model_runtime_mode.lower() != "live":
        return MockVisionProvider()
    if normalized in {"", "mock"}:
        raise ConfigurationError("Live runtime requires at least one real vision provider")
    if normalized == "openai_compatible":
        return OpenAICompatibleVisionProvider(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
        )
    raise ConfigurationError(f"Unsupported vision provider: {provider}")


def _load_json(raw: str) -> dict[str, object]:
    """兼容 Markdown 代码块包裹的 JSON 输出。"""
    normalized = raw.strip()
    if normalized.startswith("```"):
        normalized = normalized.strip("`")
        if normalized.lower().startswith("json"):
            normalized = normalized[4:].strip()
    return json.loads(normalized)


def _merge_vocab_candidates(filename_tags: list[str], defaults: list[str]) -> list[str]:
    """把默认词和文件名标签合并成去重后的练习词候选。"""
    merged: list[str] = []
    seen: set[str] = set()

    for value in [*defaults, *filename_tags]:
        normalized = value.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)

    return merged[:6]
