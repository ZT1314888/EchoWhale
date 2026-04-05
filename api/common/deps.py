from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, Header
from pydantic import BaseModel

from api.common.exceptions import AuthenticationError
from api.common.ownership import build_user_owner, build_visitor_owner
from api.core.config import settings
from api.core.security import generate_visitor_id
from api.models.user_model import User
from api.services.auth_service import AuthService, get_auth_service


AuthorizationHeader = Annotated[str | None, Header()]
VisitorCookie = Annotated[str | None, Cookie(alias=settings.auth_visitor_cookie_name)]
RefreshCookie = Annotated[str | None, Cookie(alias=settings.auth_refresh_cookie_name)]


class ResourceOwnerContext(BaseModel):
    owner_id: str
    user: User | None = None
    visitor_id_to_set: str | None = None


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

    active_visitor_id = visitor_id or generate_visitor_id()
    return ResourceOwnerContext(
        owner_id=build_visitor_owner(active_visitor_id),
        visitor_id_to_set=None if visitor_id else active_visitor_id,
    )


def get_refresh_token(refresh_token: RefreshCookie = None) -> str:
    if not refresh_token:
        raise AuthenticationError("Authentication required")
    return refresh_token


def apply_visitor_cookie(owner: ResourceOwnerContext, response) -> None:
    if owner.visitor_id_to_set is None:
        return
    response.set_cookie(
        key=settings.auth_visitor_cookie_name,
        value=owner.visitor_id_to_set,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
