from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class SessionEvent(BaseModel):
    session_id: str
    event_type: str
    stage: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class VoiceSessionFact(BaseModel):
    session_id: str
    status: str
    termination_reason: str | None = None
    transcript_turn_count: int = 0
    # think 代理令牌代数：每次 bootstrap +1。代理校验链要求令牌里的 gen claim
    # 与该值一致，voice/complete 或 re-bootstrap 即令旧令牌失效（审计 F12）；
    # 默认 0 兼容迁移前的旧行语义（"无活跃绑定"）。
    token_generation: int = 0
    client_diagnostics: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
