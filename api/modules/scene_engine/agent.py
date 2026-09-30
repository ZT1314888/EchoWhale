from pydantic import ValidationError

from api.common.exceptions import ConfigurationError
from api.common.exceptions import EchoWhaleError
from api.common.exceptions import ModelProviderError
from api.common.exceptions import UnsupportedSceneImageError
from api.core.config import settings
from api.integrations.llm.resilience import LLMAttempt
from api.integrations.llm.resilience import run_llm_with_failover
from api.integrations.llm.runtime import provider_slot_from_settings
from api.integrations.llm.runtime import resolve_engine_providers
from api.modules.scene_engine.providers.vision_provider import MockVisionProvider
from api.modules.scene_engine.providers.vision_provider import OpenAICompatibleVisionProvider
from api.modules.scene_engine.providers.vision_provider import VisionProvider
from api.modules.scene_engine.schema import SceneAnalysisInput, SceneAnalysisResult


LOW_CONFIDENCE_THRESHOLD = 0.65


class SceneEngineAgent:
    def __init__(
        self,
        primary_provider: VisionProvider | None = None,
        fallback_provider: VisionProvider | None = None,
    ) -> None:
        """初始化主备视觉 provider；显式注入优先于配置解析。"""
        if primary_provider is not None:
            self.primary_provider = primary_provider
            self.fallback_provider = fallback_provider or primary_provider
            return

        self.primary_provider, self.fallback_provider = resolve_engine_providers(
            kind="vision",
            primary_slot=provider_slot_from_settings("vision", "primary"),
            fallback_slot=provider_slot_from_settings("vision", "fallback"),
            build_mock=lambda: MockVisionProvider(),
            build_real=lambda slot: OpenAICompatibleVisionProvider(
                base_url=slot.base_url,
                api_key=slot.api_key,
                model=slot.model,
                timeout_seconds=slot.timeout_seconds,
            ),
        )

    async def run(self, payload: SceneAnalysisInput) -> SceneAnalysisResult:
        """优先走主 provider：瞬时错误带退避重试，仍失败则切到回退 provider。"""
        attempts = [
            LLMAttempt(
                name="vision_primary",
                call=lambda: self._analyze_with_provider(
                    provider=self.primary_provider,
                    payload=payload,
                    provider_name="primary",
                ),
            )
        ]
        if self.fallback_provider is not self.primary_provider:
            attempts.append(
                LLMAttempt(
                    name="vision_fallback",
                    call=lambda: self._analyze_with_provider(
                        provider=self.fallback_provider,
                        payload=payload,
                        provider_name="fallback",
                    ),
                )
            )
        return await run_llm_with_failover(
            attempts,
            retries_per_provider=settings.llm_max_retries_per_provider,
            retry_backoff_seconds=settings.llm_retry_backoff_seconds,
            deadline_seconds=settings.llm_request_deadline_seconds,
            compose_failure=_compose_scene_failures,
        )

    async def _analyze_with_provider(
        self,
        *,
        provider: VisionProvider,
        payload: SceneAnalysisInput,
        provider_name: str,
    ) -> SceneAnalysisResult:
        """统一封装 provider 调用、schema 校验和练习可用性门禁。"""
        try:
            raw_result = await provider.analyze(payload)
        except EchoWhaleError:
            raise
        except Exception as exc:
            raise ModelProviderError(f"{provider_name} vision provider crashed") from exc

        try:
            result = SceneAnalysisResult.model_validate(raw_result)
        except ValidationError as exc:
            raise ModelProviderError(
                f"{provider_name} vision provider returned invalid scene output"
            ) from exc

        if result.confidence < LOW_CONFIDENCE_THRESHOLD:
            # 低置信度结果在交互上通常等价于“这张图不适合练习”。
            raise UnsupportedSceneImageError(
                "Unsupported scene image",
                data={"reason": "scene_not_practice_ready", "retryable": False},
            )
        if not result.visual_anchors or not result.vocab_candidates:
            raise UnsupportedSceneImageError(
                "Unsupported scene image",
                data={"reason": "scene_not_practice_ready", "retryable": False},
            )
        return result

def _compose_scene_failures(failures: list[tuple[str, Exception]]) -> EchoWhaleError:
    """把主备 provider 的失败原因归并成可对外暴露的统一错误。"""
    errors = [error for _, error in failures]
    if errors and all(isinstance(error, UnsupportedSceneImageError) for error in errors):
        # 仅当所有 provider 都认定图片不适合练习时，才按业务门禁错误返回。
        return UnsupportedSceneImageError(
            "Unsupported scene image",
            data={"reason": "scene_not_practice_ready", "retryable": False},
        )

    summary = "; ".join(f"{name}={error}" for name, error in failures) or "unknown provider failure"
    return ModelProviderError(f"Scene engine failed after fallback: {summary}")
