from pydantic import BaseModel


class SceneState(BaseModel):
    last_scene: str | None = None
