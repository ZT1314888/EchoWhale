from __future__ import annotations

import logging
from json import JSONDecodeError
from typing import Any
from typing import Iterator

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from fastapi.responses import StreamingResponse
import httpx
from pydantic import BaseModel
from pydantic import ValidationError
from pydantic import field_validator

from api.common.exceptions import AuthenticationError
from api.common.exceptions import ConfigurationError
from api.core.config import settings
from api.integrations.deepgram import build_deepgram_think_upstream_url
from api.integrations.deepgram import DeepgramThinkProxyTokenCodec
from api.integrations.deepgram import validate_deepgram_think_upstream_settings


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
        logger.warning("Deepgram think proxy received invalid JSON payload for session=%s", session_id)
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

    if _requests_streaming(payload):
        return _stream_think_response(payload=payload, session_id=session_id)

    try:
        with httpx.Client(timeout=settings.deepgram_agent_think_timeout_seconds) as client:
            response = client.post(
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
        logger.error(
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


def _stream_think_response(
    *,
    payload: dict[str, Any],
    session_id: str,
) -> Response:
    client = httpx.Client(timeout=settings.deepgram_agent_think_timeout_seconds)
    try:
        upstream_request = client.build_request(
            "POST",
            build_deepgram_think_upstream_url(),
            headers=_build_upstream_headers(),
            json=payload,
        )
        response = client.send(upstream_request, stream=True)
    except httpx.HTTPError:
        _close_client(client)
        return _error_response(
            status_code=502,
            message="Deepgram think upstream request failed",
            error_type="upstream_error",
        )

    content_type = response.headers.get("content-type", "")
    if _is_sse_response(content_type):
        return StreamingResponse(
            _iter_sse_bytes(response=response, client=client),
            status_code=response.status_code,
            headers=_build_sse_response_headers(response.headers),
            media_type="text/event-stream",
        )

    try:
        body = response.read()
    finally:
        response.close()
        _close_client(client)

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


def _iter_sse_bytes(*, response: httpx.Response, client: httpx.Client) -> Iterator[bytes]:
    try:
        yield from response.iter_bytes()
    finally:
        response.close()
        _close_client(client)


def _build_sse_response_headers(headers: httpx.Headers) -> dict[str, str]:
    response_headers: dict[str, str] = {}
    cache_control = headers.get("cache-control")
    if cache_control:
        response_headers["Cache-Control"] = cache_control
    return response_headers


def _close_client(client: httpx.Client) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        close()
