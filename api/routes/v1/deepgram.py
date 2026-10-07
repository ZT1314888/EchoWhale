from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from functools import lru_cache
from json import JSONDecodeError
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ValidationError, field_validator

from api.common.exceptions import (
    AuthenticationError,
    ConfigurationError,
    NotFoundError,
    TooManyRequestsError,
)
from api.common.request_context import (
    reset_request_owner,
    reset_request_session,
    set_request_owner,
    set_request_session,
)
from api.core.config import settings
from api.db.session_db import SessionRepository, build_session_repository
from api.integrations.deepgram import (
    DEEPGRAM_THINK_PROXY_GENERATION_CLAIM,
    DeepgramThinkProxyTokenCodec,
    build_deepgram_think_upstream_url,
    validate_deepgram_think_upstream_settings,
)
from api.services.llm_rate_limit import LLMRateLimiter, get_llm_rate_limiter

router = APIRouter(prefix="/deepgram", tags=["deepgram"])
logger = logging.getLogger(__name__)


class ProxyMessage(BaseModel):
    role: str
    content: str | list[dict[str, object]]

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"system", "user", "assistant", "tool"}:
            raise ValueError("Invalid message role")
        return normalized


class ProxyChatCompletionRequest(BaseModel):
    model: str
    messages: list[ProxyMessage]
    stream: bool = False


@router.post("/think/chat/completions")
async def proxy_deepgram_think_chat_completions(
    request: Request,
    authorization: str | None = Header(default=None),
    session_repository: SessionRepository = Depends(build_session_repository),
    rate_limiter: LLMRateLimiter = Depends(get_llm_rate_limiter),
) -> Response:
    token = _extract_bearer_token(authorization)
    if token is None:
        return _error_response(
            status_code=401,
            message="Proxy authorization required",
            error_type="authentication_error",
        )

    try:
        claims = DeepgramThinkProxyTokenCodec().decode(token)
    except AuthenticationError:
        return _error_response(
            status_code=401,
            message="Proxy authorization required",
            error_type="authentication_error",
        )
    session_id = _extract_session_id(claims)
    generation = _extract_generation(claims)

    try:
        validate_deepgram_think_upstream_settings()
    except ConfigurationError:
        logger.exception("Deepgram think proxy misconfigured for session=%s", session_id)
        return _error_response(
            status_code=500,
            message="Deepgram think proxy is not configured",
            error_type="configuration_error",
        )

    try:
        payload = await request.json()
    except JSONDecodeError:
        logger.warning(
            "Deepgram think proxy received invalid JSON payload for session=%s", session_id
        )
        return _error_response(
            status_code=400,
            message="Invalid proxy request payload",
            error_type="invalid_request_error",
        )

    validation_error = _validate_proxy_payload(payload)
    if validation_error is not None:
        logger.warning(
            "Deepgram think proxy rejected invalid request for session=%s error=%s",
            session_id,
            validation_error,
        )
        return _error_response(
            status_code=400,
            message=validation_error,
            error_type="invalid_request_error",
        )

    # 顺序理由（审计 Finding 12b）：per-sid 限流先于存在性校验——同 sid 洪泛
    # 在配额打满后即被挡，不再打 DB；伪造令牌则进不到 sid 提取。令牌 TTL 内
    # 可复用，per-sid 配额是这种可复用性的主要约束。
    try:
        rate_limiter.consume(action="think_proxy", key=session_id)
    except TooManyRequestsError:
        logger.warning("Deepgram think proxy rate limited for session=%s", session_id)
        return _error_response(
            status_code=429,
            message="Too many requests for this session",
            error_type="rate_limit_error",
        )

    # sid 存在性校验：令牌是 TTL 内可复用的 bearer 能力，签发后不再与应用状态
    # 绑定，这里用仓储 PK 查询把"令牌有效"收紧到"会话仍存在"。不存在（含
    # sid="unknown"）统一 401 authentication_error，不泄露会话存在性。
    try:
        session_head = await session_repository.get_session_head(session_id)
    except NotFoundError:
        logger.warning("Deepgram think proxy rejected unknown session id")
        return _error_response(
            status_code=401,
            message="Proxy authorization required",
            error_type="authentication_error",
        )

    # 生命周期绑定（审计 F12 Better fix）：令牌必须命中当前活跃的语音会话
    # 代数——fact 不存在（从未 bootstrap）、已收口（voice/complete）、代数落后
    # （re-bootstrap 过）或令牌缺 gen claim（部署前签发的旧令牌）一律 401。
    # 拒绝原因只进服务端日志，响应与既有 401 同形，防枚举。fact 是 PK 点查，
    # 与上一条 sid 存在性同级别；不合并 JOIN——head 承担归属接缝，fact 承担
    # 生命周期，各自复用既有仓储方法。
    voice_fact = await session_repository.get_latest_voice_session_fact(session_id)
    if (
        generation is None
        or voice_fact is None
        or voice_fact.status != "active"
        or voice_fact.token_generation != generation
    ):
        reason = (
            "missing_generation_claim"
            if generation is None
            else (
                "missing_fact"
                if voice_fact is None
                else "inactive_fact" if voice_fact.status != "active" else "generation_mismatch"
            )
        )
        logger.warning(
            "Deepgram think proxy rejected stale token for session=%s reason=%s",
            session_id,
            reason,
        )
        return _error_response(
            status_code=401,
            message="Proxy authorization required",
            error_type="authentication_error",
        )

    # think 代理的归因接缝：请求身份是 service token（typ=deepgram-think-proxy），
    # 过不了 get_resource_owner 依赖链的 access-token 校验——owner 走依赖形态会
    # 把 Deepgram 回源请求整体 401。会话存在性确认后从会话头取归属：user_id 即
    # owner_id 形态（user:/visitor:），与 get_attribution_owner 产物同构；
    # session 归因同样在此建立。upstream 调用结束后 finally 复位。
    owner_token = set_request_owner(session_head.user_id)
    session_token = set_request_session(session_id)
    try:
        if _requests_streaming(payload):
            return await _stream_think_response(payload=payload, session_id=session_id)

        try:
            response = await _get_deepgram_async_client().post(
                build_deepgram_think_upstream_url(),
                headers=_build_upstream_headers(),
                json=payload,
            )
        except httpx.HTTPError:
            return _error_response(
                status_code=502,
                message="Deepgram think upstream request failed",
                error_type="upstream_error",
            )

        try:
            content = response.json()
        except ValueError:
            logger.exception(
                "Deepgram think upstream returned non-JSON response for session=%s status=%s body_bytes=%s",
                session_id,
                response.status_code,
                len(response.content),
            )
            return _error_response(
                status_code=502,
                message="Deepgram think upstream returned a non-JSON response",
                error_type="upstream_invalid_response",
            )

        if response.status_code >= 400:
            logger.warning(
                "Deepgram think upstream error for session=%s status=%s error_type=%s",
                session_id,
                response.status_code,
                _extract_error_type(content),
            )

        return JSONResponse(content=content, status_code=response.status_code)
    finally:
        reset_request_session(session_token)
        reset_request_owner(owner_token)


async def _stream_think_response(
    *,
    payload: dict[str, Any],
    session_id: str,
) -> Response:
    client = _get_deepgram_async_client()
    try:
        upstream_request = client.build_request(
            "POST",
            build_deepgram_think_upstream_url(),
            headers=_build_upstream_headers(),
            json=payload,
        )
        response = await client.send(upstream_request, stream=True)
    except httpx.HTTPError:
        return _error_response(
            status_code=502,
            message="Deepgram think upstream request failed",
            error_type="upstream_error",
        )

    content_type = response.headers.get("content-type", "")
    if _is_sse_response(content_type):
        return StreamingResponse(
            _iter_sse_bytes(response=response),
            status_code=response.status_code,
            headers=_build_sse_response_headers(response.headers),
            media_type="text/event-stream",
        )

    try:
        body = await response.aread()
    finally:
        await response.aclose()

    if _is_json_response(content_type):
        try:
            content = response.json()
        except ValueError:
            pass
        else:
            if response.status_code >= 400:
                logger.warning(
                    "Deepgram think upstream error for session=%s status=%s error_type=%s",
                    session_id,
                    response.status_code,
                    _extract_error_type(content),
                )
            return JSONResponse(content=content, status_code=response.status_code)

    logger.error(
        "Deepgram think upstream returned non-JSON response for session=%s status=%s body_bytes=%s",
        session_id,
        response.status_code,
        len(body),
    )
    return _error_response(
        status_code=502,
        message="Deepgram think upstream returned a non-JSON response",
        error_type="upstream_invalid_response",
    )


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _error_response(*, status_code: int, message: str, error_type: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "message": message,
                "type": error_type,
            }
        },
    )


def _extract_session_id(claims: dict[str, Any]) -> str:
    session_id = claims.get("sid")
    return session_id if isinstance(session_id, str) and session_id else "unknown"


def _extract_generation(claims: dict[str, Any]) -> int | None:
    """读取令牌里的代数 claim；缺失或类型不对返回 None（校验链按不匹配拒绝）。

    bool 是 int 的子类，必须显式排除，否则 True 会顶替代数 1 通过校验。
    """
    value = claims.get(DEEPGRAM_THINK_PROXY_GENERATION_CLAIM)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _extract_error_type(payload: Any) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            error_type = error.get("type")
            if isinstance(error_type, str) and error_type:
                return error_type
    return "unknown"


def _build_upstream_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.deepgram_agent_think_upstream_api_key}",
    }


def _requests_streaming(payload: dict[str, Any]) -> bool:
    return payload.get("stream") is True


def _validate_proxy_payload(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return "Invalid proxy request payload"

    try:
        request = ProxyChatCompletionRequest.model_validate(payload)
    except ValidationError:
        return "Invalid proxy request payload"

    allowed_model = settings.deepgram_agent_think_model.strip()
    if allowed_model and request.model != allowed_model:
        return "Requested model is not allowed for this proxy"

    return None


def _is_sse_response(content_type: str) -> bool:
    return content_type.split(";", 1)[0].strip().lower() == "text/event-stream"


def _is_json_response(content_type: str) -> bool:
    return content_type.split(";", 1)[0].strip().lower() == "application/json"


async def _iter_sse_bytes(*, response: httpx.Response) -> AsyncIterator[bytes]:
    try:
        async for chunk in response.aiter_bytes():
            yield chunk
    finally:
        await response.aclose()


def _build_sse_response_headers(headers: httpx.Headers) -> dict[str, str]:
    response_headers: dict[str, str] = {}
    cache_control = headers.get("cache-control")
    if cache_control:
        response_headers["Cache-Control"] = cache_control
    return response_headers


@lru_cache(maxsize=4)
def _build_deepgram_async_client(timeout_seconds: int) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout_seconds)


def _get_deepgram_async_client() -> httpx.AsyncClient:
    return _build_deepgram_async_client(settings.deepgram_agent_think_timeout_seconds)
