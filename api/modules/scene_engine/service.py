from api.modules.scene_engine.agent import SceneEngineAgent
from api.modules.scene_engine.providers.vision_provider import VisionProvider
from api.modules.scene_engine.schema import SceneAnalysisInput, SceneAnalysisResult
from api.modules.scene_engine.tools.image_quality import SceneImageQualityGate


class SceneEngineService:
    def __init__(
        self,
        *,
        primary_provider: VisionProvider | None = None,
        fallback_provider: VisionProvider | None = None,
        quality_gate: SceneImageQualityGate | None = None,
    ) -> None:
        self.agent = SceneEngineAgent(
            primary_provider=primary_provider,
            fallback_provider=fallback_provider,
        )
        self.quality_gate = quality_gate or SceneImageQualityGate()

    def analyze(self, filename: str, media_url: str) -> SceneAnalysisResult:
        payload = SceneAnalysisInput(filename=filename, media_url=media_url)
        self.quality_gate.screen(payload)
        return self.agent.run(payload)
