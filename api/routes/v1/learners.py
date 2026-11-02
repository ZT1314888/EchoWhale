"""学员档案读 API：GET /learners/me/profile（薄路由，无限流）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from api.common.deps import require_authenticated_user
from api.common.ownership import build_user_owner
from api.common.responses import ApiResponse
from api.contracts.learner import LearnerProfileResponse
from api.models.user_model import User
from api.services.learner_profile_service import LearnerProfileService

router = APIRouter(prefix="/learners", tags=["learners"])


def get_learner_profile_service() -> LearnerProfileService:
    return LearnerProfileService()


@router.get("/me/profile", response_model=ApiResponse[LearnerProfileResponse])
async def get_my_learner_profile(
    profile_service: LearnerProfileService = Depends(get_learner_profile_service),
    current_user: User = Depends(require_authenticated_user),
) -> Any:
    """当前认证用户的滚动学习档案（只读）。

    - 认证必需：访客 / 匿名（无或坏 Bearer）在依赖处即 401（code 1002），
      访客根本到不了业务逻辑，因此无需 apply_visitor_cookie；
    - 空档案（首访用户，仓库 get 返回 None）返回 200 全空载荷而非 404：
      空态是合法展示态，前端以 practiced_turn_count == 0 判空并渲染引导文案；
    - 无限流：与其他 GET 端点一致（纯读点查，无 LLM 成本面）。
    """
    profile = await profile_service.get_profile(build_user_owner(current_user.id))
    return ApiResponse.success(data=LearnerProfileResponse.from_profile(profile))
