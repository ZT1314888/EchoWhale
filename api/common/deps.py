from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Cookie, Depends, Header
from pydantic import BaseModel

from api.common.exceptions import AuthenticationError
from api.common.ownership import build_user_owner, build_visitor_owner
from api.common.request_context import reset_request_owner, set_request_owner
from api.core.config import settings
from api.core.security import generate_visitor_id, sign_value, verify_signed_value
from api.models.user_model import User
from api.services.auth_service import AuthService, get_auth_service

AuthorizationHeader = Annotated[str | None, Header()]
VisitorCookie = Annotated[str | None, Cookie(alias=settings.auth_visitor_cookie_name)]
RefreshCookie = Annotated[str | None, Cookie(alias=settings.auth_refresh_cookie_name)]


class ResourceOwnerContext(BaseModel):
    owner_id: str
    user: User | None = None
    visitor_id_to_set: str | None = None

    @property
    def is_anonymous(self) -> bool:
        """匿名访客判定：路由层据此决定是否追加 IP 维度的兜底限流。"""
        return self.user is None


def get_optional_authenticated_user(
    authorization: AuthorizationHeader = None,
    auth_service: AuthService = Depends(get_auth_service),
) -> User | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationError("Authentication required")
    return auth_service.get_current_user(access_token=token)


def require_authenticated_user(
    current_user: User | None = Depends(get_optional_authenticated_user),
) -> User:
    if current_user is None:
        raise AuthenticationError("Authentication required")
    return current_user


def get_resource_owner(
    current_user: User | None = Depends(get_optional_authenticated_user),
    visitor_id: VisitorCookie = None,
) -> ResourceOwnerContext:
    if current_user is not None:
        return ResourceOwnerContext(
            owner_id=build_user_owner(current_user.id),
            user=current_user,
        )

    # Cookie 必须先验签：值虽由服务端签发，但客户端可任意伪造或携带旧版
    # 未签名值。验签不过一律视为"没有访客身份"（fail-closed 重新签发），
    # 伪造字符串绝不能进入 owner_id / 限流键 / 存储路径，也不报错打断匿名流程。
    verified_visitor_id = verify_signed_value(visitor_id, secret=settings.auth_jwt_secret)
    if verified_visitor_id is not None:
        return ResourceOwnerContext(
            owner_id=build_visitor_owner(verified_visitor_id),
            visitor_id_to_set=None,
        )

    fresh_visitor_id = generate_visitor_id()
    return ResourceOwnerContext(
        owner_id=build_visitor_owner(fresh_visitor_id),
        visitor_id_to_set=fresh_visitor_id,
    )


async def get_attribution_owner(
    owner: ResourceOwnerContext = Depends(get_resource_owner),
) -> AsyncIterator[ResourceOwnerContext]:
    """owner 归因 yield 依赖：进入时把 owner_id 写入请求上下文，响应完成后复位。

    为什么包一层 yield 而不改 get_resource_owner 本体：它被大量路由消费，转
    yield 影响面大；仅 LLM 消耗路由换用本依赖。yield 依赖的 teardown 在响应
    （含流式体）发送完成后才执行，SSE 流末帧的用量归因不会被过早擦除。
    为什么必须是 async 依赖：同步依赖会被 FastAPI 挪进线程池执行，ContextVar
    的 set 会留在工作线程上下文里，事件循环上的 handler 读不到。
    """
    token = set_request_owner(owner.owner_id)
    try:
        yield owner
    finally:
        reset_request_owner(token)


def get_refresh_token(refresh_token: RefreshCookie = None) -> str:
    if not refresh_token:
        raise AuthenticationError("Authentication required")
    return refresh_token


def apply_visitor_cookie(owner: ResourceOwnerContext, response) -> None:
    if owner.visitor_id_to_set is None:
        return
    response.set_cookie(
        key=settings.auth_visitor_cookie_name,
        # 写入签名值：下次请求 get_resource_owner 验签通过才会采信，
        # 客户端无法构造出能通过验签的自选 visitor_id。
        value=sign_value(owner.visitor_id_to_set, secret=settings.auth_jwt_secret),
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
