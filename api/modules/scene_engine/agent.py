from pydantic import ValidationError

from api.common.exceptions import EchoWhaleError
from api.common.exceptions import ConfigurationError
from api.common.exceptions import ModelProviderError
from api.common.exceptions import UnsupportedSceneImageError
from api.core.config import settings
from api.modules.scene_engine.providers.vision_provider import VisionProvider
from api.modules.scene_engine.providers.vision_provider import build_fallback_vision_provider
from api.modules.scene_engine.providers.vision_provider import build_primary_vision_provider
from api.modules.scene_engine.providers.vision_provider import has_real_vision_provider
from api.modules.scene_engine.schema import SceneAnalysisInput, SceneAnalysisResult


LOW_CONFIDENCE_THRESHOLD = 0.65


class SceneEngineAgent:
    def __init__(
        self,
        primary_provider: VisionProvider | None = None,
        fallback_provider: VisionProvider | None = None,
    ) -> None:
        """初始化主备视觉 provider，并处理 live/mock 模式分流。"""
        if primary_provider is not None:
            self.primary_provider = primary_provider
            self.fallback_provider = fallback_provider or primary_provider
            return

        if settings.model_runtime_mode.lower() == "live":
            has_primary = has_real_vision_provider(settings.vision_primary_provider)
            has_fallback = has_real_vision_provider(settings.vision_fallback_provider)
            if not has_primary and not has_fallback:
                raise ConfigurationError("Live runtime requires at least one real vision provider")
            if has_primary:
                self.primary_provider = build_primary_vision_provider()
                self.fallback_provider = (
                    fallback_provider
                    or build_fallback_vision_provider()
                    if has_fallback
                    else self.primary_provider
                )
                return
            resolved_fallback = fallback_provider or build_fallback_vision_provider()
            self.primary_provider = resolved_fallback
            self.fallback_provider = resolved_fallback
            return

        self.primary_provider = build_primary_vision_provider()
        self.fallback_provider = fallback_provider or build_fallback_vision_provider()

    async def run(self, payload: SceneAnalysisInput) -> SceneAnalysisResult:
        """优先走主 provider，失败后在可行时自动切到回退 provider。"""
        primary_error: Exception | None = None
        try:
            return await self._analyze_with_provider(
                provider=self.primary_provider,
                payload=payload,
                provider_name="primary",
            )
        except Exception as exc:
            primary_error = exc

        if self.fallback_provider is self.primary_provider:
            raise self._compose_failure(primary_error, None)

        try:
            return await self._analyze_with_provider(
                provider=self.fallback_provider,
                payload=payload,
                provider_name="fallback",
            )
        except Exception as fallback_error:
            raise self._compose_failure(primary_error, fallback_error) from fallback_error

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

    def _compose_failure(
        self,
        primary_error: Exception | None,
        fallback_error: Exception | None,
    ) -> EchoWhaleError:
        """把主备 provider 的失败原因归并成可对外暴露的统一错误。"""
        if fallback_error is None and isinstance(primary_error, EchoWhaleError):
            return primary_error

        if _all_unsupported_scene_errors(primary_error, fallback_error):
            return UnsupportedSceneImageError(
                "Unsupported scene image",
                data={"reason": "scene_not_practice_ready", "retryable": False},
            )

        reasons = []
        if primary_error is not None:
            reasons.append(f"primary={primary_error}")
        if fallback_error is not None:
            reasons.append(f"fallback={fallback_error}")
        summary = "; ".join(reasons) or "unknown provider failure"
        return ModelProviderError(f"Scene engine failed after fallback: {summary}")


def _all_unsupported_scene_errors(*errors: Exception | None) -> bool:
    """仅当所有真实错误都表明图片不适合练习时才返回真。"""
    present_errors = [error for error in errors if error is not None]
    return bool(present_errors) and all(
        isinstance(error, UnsupportedSceneImageError) for error in present_errors
    )
