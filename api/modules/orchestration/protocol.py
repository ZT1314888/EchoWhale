"""Agent 协作协议与注册表（多 Agent 升级 P0 · 缺口 G1/G6）。

设计依据：docs/proposals/multi_agent_upgrade/02_target_architecture.md §2.1/§3.1/§3.3。

- 本项目一轮对话是**确定性管道 + 固定并发分支**（feedback ∥ coach → review），
  不做动态路由（拒用 LangGraph 的同一理由，§2.1）。因此注册表不承担主链路
  分派，只承担两件事：
  1) 角色协议（`ConversationCoachAgent` / `FeedbackReviewAgent` /
     `ReviewSummarizerProtocol`）显式声明三个既有 agent 的协作面——编排层与
     门面按协议传参，「谁调用谁、失败谁降级」在类型上可读；
  2) 增强型 agent（P1 发音 / P2 记忆·课程）实现 `EnhancementAgent` 协议后在
     注册表登记，新增 agent 全程不改编排器主干（P0 用户故事）。
- 三值终态（ok/degraded/failed）与 `api/common/telemetry.py` 的常量严格同值；
  telemetry 负责记账（span 属性），本模块只做类型化，不重复记账。
- 注册表保存描述符与实现引用，是目录与契约检查点，不是服务定位器：主链路
  依赖仍由门面在调用时显式解析（保留测试可替换引擎的晚绑定契约）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from api.models.message_model import Message
from api.modules.coach_engine.schema import CoachReplyResult
from api.modules.feedback_engine.schema import FeedbackResult
from api.modules.session_engine.review_builder import ReviewCopy


class CoachReplyStream(Protocol):
    """教练回复增量流协作面：`SingleDeltaTextStream` / `WordChunkedTextStream` /
    `HttpxTextStream`（integrations/llm/streaming.py）共有的最小接口。"""

    async def aiter_deltas(self) -> AsyncIterator[str]: ...

    async def aclose(self) -> None: ...


class EngineTerminalState(StrEnum):
    """三值终态：取值与 telemetry.TERMINAL_{OK,DEGRADED,FAILED} 严格一致。"""

    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"


class AgentDescriptor(BaseModel):
    """注册表条目的静态描述：职责、失败语义与模型档次（§3.1 角色清单字段）。"""

    name: str
    role: str
    failure_policy: str
    model_tier: str = "none"


class AgentRequest(BaseModel):
    """增强型 agent 的统一请求信封：路由元数据 + 自由结构化负载。

    主链路三个角色的签名是领域定制的（见各自 Protocol），不走信封；信封服务
    于 P1/P2 新增 agent，负载 schema 由各 agent 自行定义与校验。
    """

    agent_name: str
    session_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    """增强型 agent 的统一结果信封：三值终态 + 结构化产出与错误摘要。"""

    agent_name: str
    outcome: EngineTerminalState
    payload: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class AgentRegistrationError(Exception):
    """同名重复注册：注册表拒绝静默覆盖，避免运行期悄悄换实现。"""


@runtime_checkable
class EnhancementAgent(Protocol):
    """P1/P2 新增 agent 的最小协作协议：命名 + 统一信封调用。"""

    name: str

    async def invoke(self, request: AgentRequest) -> AgentResult: ...


@runtime_checkable
class ConversationCoachAgent(Protocol):
    """对话教练协作面：整包与流式两种产出形态（coach_engine/service.py）。"""

    async def respond(
        self,
        scene: str,
        role: str,
        learner_message: str,
        visual_anchors: list[str],
        vocab_candidates: list[str],
        recent_messages: list[Message],
        learner_context: str | None = None,
        learner_cefr: str | None = None,
    ) -> CoachReplyResult: ...

    async def stream_respond(
        self,
        scene: str,
        role: str,
        learner_message: str,
        visual_anchors: list[str],
        vocab_candidates: list[str],
        recent_messages: list[Message],
        learner_context: str | None = None,
        learner_cefr: str | None = None,
    ) -> CoachReplyStream: ...


@runtime_checkable
class FeedbackReviewAgent(Protocol):
    """反馈教练协作面：学习者消息 + 场景 → 结构化反馈 JSON。"""

    async def review(
        self,
        learner_message: str,
        scene: str,
        vocab_candidates: list[str],
        learner_context: str | None = None,
    ) -> FeedbackResult: ...


@runtime_checkable
class ReviewSummarizerProtocol(Protocol):
    """复盘 agent 协作面：反馈 JSON → 中文复盘文案（增强分支）。"""

    async def summarize(
        self,
        *,
        scene: str,
        role: str,
        learner_message: str,
        feedback: FeedbackResult,
    ) -> ReviewCopy: ...


class AgentRegistry:
    """agent 注册表：描述符 + 实现引用的目录（契约检查点，非服务定位器）。

    同名重复注册直接抛错（拒绝静默覆盖）；`resolve` 对未登记名抛 KeyError，
    让「编排器引用了不存在的 agent」在第一次调用就暴露。
    """

    def __init__(self) -> None:
        self._entries: dict[str, tuple[AgentDescriptor, Any]] = {}

    def register(self, descriptor: AgentDescriptor, impl: Any) -> None:
        if descriptor.name in self._entries:
            raise AgentRegistrationError(f"agent already registered: {descriptor.name}")
        self._entries[descriptor.name] = (descriptor, impl)

    def resolve(self, name: str) -> Any:
        try:
            return self._entries[name][1]
        except KeyError:
            raise KeyError(f"agent not registered: {name}") from None

    def descriptor(self, name: str) -> AgentDescriptor:
        try:
            return self._entries[name][0]
        except KeyError:
            raise KeyError(f"agent not registered: {name}") from None

    def names(self) -> list[str]:
        return list(self._entries)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._entries

    def __len__(self) -> int:
        return len(self._entries)
