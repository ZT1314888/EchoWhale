from api.modules.scene_engine.providers.vision_provider import MockVisionProvider
from api.modules.scene_engine.schema import SceneAnalysisInput, SceneAnalysisResult


class SceneEngineAgent:
    def __init__(self) -> None:
        self.provider = MockVisionProvider()

    def run(self, payload: SceneAnalysisInput) -> SceneAnalysisResult:
        return self.provider.analyze(payload)
