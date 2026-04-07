from pydantic import ValidationError

from api.common.exceptions import EchoWhaleError
from api.common.exceptions import ModelProviderError
from api.common.exceptions import UnsupportedSceneImageError
from api.modules.scene_engine.providers.vision_provider import VisionProvider
from api.modules.scene_engine.providers.vision_provider import build_fallback_vision_provider
from api.modules.scene_engine.providers.vision_provider import build_primary_vision_provider
from api.modules.scene_engine.schema import SceneAnalysisInput, SceneAnalysisResult


LOW_CONFIDENCE_THRESHOLD = 0.65


class SceneEngineAgent:
    def __init__(
        self,
        primary_provider: VisionProvider | None = None,
        fallback_provider: VisionProvider | None = None,
    ) -> None:
        self.primary_provider = primary_provider or build_primary_vision_provider()
        self.fallback_provider = fallback_provider or build_fallback_vision_provider()

    def run(self, payload: SceneAnalysisInput) -> SceneAnalysisResult:
        primary_error: Exception | None = None
        try:
            return self._analyze_with_provider(
                provider=self.primary_provider,
                payload=payload,
                provider_name="primary",
            )
        except Exception as exc:
            primary_error = exc

        if self.fallback_provider is self.primary_provider:
            raise self._compose_failure(primary_error, None)

        try:
            return self._analyze_with_provider(
                provider=self.fallback_provider,
                payload=payload,
                provider_name="fallback",
            )
        except Exception as fallback_error:
            raise self._compose_failure(primary_error, fallback_error) from fallback_error

    def _analyze_with_provider(
        self,
        *,
        provider: VisionProvider,
        payload: SceneAnalysisInput,
        provider_name: str,
    ) -> SceneAnalysisResult:
        try:
            raw_result = provider.analyze(payload)
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
    present_errors = [error for error in errors if error is not None]
    return bool(present_errors) and all(
        isinstance(error, UnsupportedSceneImageError) for error in present_errors
    )
