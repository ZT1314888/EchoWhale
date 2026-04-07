from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator, model_validator


def _normalize_scene(value: object) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _normalize_phrase(value: object) -> str:
    return re.sub(r"\s+", " ", str(value).strip())


def _normalize_keywords(value: object, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")

    normalized_labels: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = _normalize_phrase(item).lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_labels.append(normalized)
    return normalized_labels


class SceneAnalysisInput(BaseModel):
    filename: str
    media_url: str


class SceneAnalysisResult(BaseModel):
    scene: str
    role: str
    opener: str
    visual_anchors: list[str] = Field(default_factory=list)
    vocab_candidates: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    confidence: float

    @field_validator("scene", mode="before")
    @classmethod
    def normalize_scene(cls, value: object) -> str:
        normalized = _normalize_scene(value)
        if not normalized:
            raise ValueError("scene must not be empty")
        return normalized

    @field_validator("role", "opener", mode="before")
    @classmethod
    def normalize_text_fields(cls, value: object) -> str:
        normalized = _normalize_phrase(value)
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized

    @field_validator("visual_anchors", "vocab_candidates", "labels", mode="before")
    @classmethod
    def normalize_keyword_fields(cls, value: object, info) -> list[str]:
        return _normalize_keywords(value, field_name=info.field_name)

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @model_validator(mode="after")
    def fill_compatibility_keywords(self) -> "SceneAnalysisResult":
        if self.labels and not self.vocab_candidates and not self.visual_anchors:
            self.vocab_candidates = list(self.labels)

        aggregate = []
        seen: set[str] = set()
        for value in [*self.visual_anchors, *self.vocab_candidates]:
            if value in seen:
                continue
            seen.add(value)
            aggregate.append(value)

        self.labels = aggregate or list(self.labels)
        return self
