"""学员档案只读用例：读 API 直持仓库做 PK 点查。

为什么不经 SessionEngineService / agent：读端点是单行点查，为它拉起完整编排器
（R2 signer、media/session 仓库）不成比例，且专用依赖名让 dependency_overrides
的测试替身更干净。失败语义也不同——写路径 agent._load_learner_profile 捕获异常
降级为 None（回复轮增强分支的正确语义），但那会把存储故障伪装成"空档案"；
读路径必须如实上抛，由全局异常处理器渲染 500 信封，绝不做降级吞错。
"""

from __future__ import annotations

from api.db.learner_profile_db import (
    LearnerProfileRepository,
    build_learner_profile_repository,
)
from api.models.learner_profile_model import LearnerProfile


class LearnerProfileService:
    """学员档案读取服务：仓库 get 透传，无缓存、无降级。"""

    def __init__(self, repository: LearnerProfileRepository | None = None) -> None:
        self._repository = repository or build_learner_profile_repository()

    async def get_profile(self, user_id: str) -> LearnerProfile | None:
        """PK 点查学员档案；首访用户（无档案行）返回 None，由契约层渲染空态。"""
        return await self._repository.get(user_id)
