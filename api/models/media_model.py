from pydantic import BaseModel, Field


class Media(BaseModel):
    id: str
    user_id: str
    filename: str
    content_type: str
    url: str
    tags: list[str] = Field(default_factory=list)
