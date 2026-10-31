"""Agent 协作层（多 Agent 升级 P0）：协议、注册表、失败策略与编排水务。

入口约定（02_target_architecture.md §3.3）：`session_engine/agent.py` 保留门面
转发；新增 agent 实现 `protocol.EnhancementAgent` 后在注册表登记，编排器主干
不改。主链路（feedback ∥ coach → review）是确定性管道，依赖由门面调用时解析。
"""

from api.modules.orchestration.failure_policy import (
    build_degraded_feedback,
    degraded_feedback_with_log,
    resolve_feedback,
)
from api.modules.orchestration.profile_branch import LearnerProfileBranch
from api.modules.orchestration.protocol import (
    AgentDescriptor,
    AgentRegistrationError,
    AgentRegistry,
    AgentRequest,
    AgentResult,
    ConversationCoachAgent,
    EngineTerminalState,
    EnhancementAgent,
    FeedbackReviewAgent,
    ReviewSummarizerProtocol,
)
from api.modules.orchestration.reply_flow import (
    build_reply_turn,
    run_reply_turn,
    stream_reply_turn,
)
from api.modules.orchestration.voice_flow import run_voice_closeout

__all__ = [
    "AgentDescriptor",
    "AgentRegistrationError",
    "AgentRegistry",
    "AgentRequest",
    "AgentResult",
    "ConversationCoachAgent",
    "EngineTerminalState",
    "EnhancementAgent",
    "FeedbackReviewAgent",
    "LearnerProfileBranch",
    "ReviewSummarizerProtocol",
    "build_degraded_feedback",
    "build_reply_turn",
    "degraded_feedback_with_log",
    "resolve_feedback",
    "run_reply_turn",
    "run_voice_closeout",
    "stream_reply_turn",
]
